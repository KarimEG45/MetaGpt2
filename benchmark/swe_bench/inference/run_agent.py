# -*- coding: utf-8 -*-
# @Author  : stellahong (stellahong@fuzhi.ai)
# @Desc    :
import asyncio
import json
import re

from tenacity import retry, stop_after_attempt, wait_random_exponential

from benchmark.swe_bench.gitagent import GitAgent
from benchmark.swe_bench.inference.gen_symbol_changes import SYMBOL_CHANGES_FILE
from benchmark.swe_bench.make_datasets.make_dataset import reset_task_env
from benchmark.swe_bench.utils.jaccard_retriever import jaccard_retriever
from benchmark.swe_bench.utils.utils import extract_scripts_from_codetext
from metagpt.logs import logger
from metagpt.utils.common import CodeParser
from metagpt.utils.exceptions import handle_exception
from metagpt.utils.recovery_util import save_history

PATCH_FORMAT = """
```diff
--- original_file.py
+++ modified_file.py
@@ -line_number,context_lines +line_number,context_lines @@
- original line of code to be replaced or removed
+ new line of code to be added or to replace the original
```
"""

LOCATING_LINE_RANGES_REQUIREMENT = """
# Instruction
Locating the code files to be modified and their line ranges, provided python dict, in the provided <code>code</code> blocks based on the given <issue>issue</issue> in the Issues and Codes containing accessible code files with {script_names}. If the code is extremely long, focus on the <issue>issue</issue> description to narrow down the areas of concern. The line ranges should be within 50-300 lines and there may be more than one range in every files.

# Think about it by following these steps:
1. Locating the files containing errors based on the <issue>issue</issue> by using a single class or function as the basic unit of investigation.
2. For each locating file:
   a. Locate the relevant code section(s) based on the <issue>issue</issue> description.
   b. Determine the line range(s) within those code sections that need to be modified.
   c. Ensure the line range(s) fall within the 50-300 line limit, adjusting as necessary.
3. Output the code files to be modified and line ranges as a dict.

# Examples:
1. If file1.py has an error in a specific function with line ranges 20-50, output dict: 
```python
{{"file1.py":["20-50"]}}
```
2. If file1.py have errors in different functions with line ranges 20-50 and 100-120 respectively, output dict: 
```python
{{"file1.py":["20-50", "100-120"]}}
```
3. If file1.py has an error in a specific function with line ranges 20-50, and file2.py have errors in different functions with line ranges 20-50 and 100-120 respectively, output dict: 
```python
{{"file1.py":["20-50"], "file2.py":["20-50", "100-120"]}}
```

# Issues and Codes
{issues_and_codes}
"""


def _prepare(inputs):
    requirement = "Please rewrite the code to address the issues. "
    system_messages = inputs.split("\n", 1)[0]
    user_message = inputs.split("\n", 1)[1]
    # Replace URLs with an empty string
    user_message = re.sub(r"https?://\S+", "", user_message)
    cleaned_user_message = re.sub("<patch>.*?</patch>", "", user_message, flags=re.DOTALL)

    issues = re.findall("<issue>(.*?)</issue>", user_message, flags=re.DOTALL)
    issues_ = re.sub(r"#{3,4} Versions.*?(?=#{3,4}|\Z)", "", issues[0], flags=re.DOTALL)
    traceback = re.findall(r"#{3,4} Actual Results.*", issues_, flags=re.DOTALL)
    issues = traceback if traceback else issues
    code = re.findall("<code>(.*?)</code>", user_message, flags=re.DOTALL)
    issues_and_code = [f"<issue>\n{issues[0]}\n</issue>", f"<code>\n{code[0]}\n</code>"]

    return requirement, system_messages, cleaned_user_message, issues_and_code


def construct_prompt(inputs, script_names):
    prompt = (
        f"You only need to modify the code file listed here {script_names}."
        f"Notice: "
        f"1. Analysis the locating range and issue, especially for the ValueError, and identify influence code lines.\n"
        f"2. Only change a few lines, and make sure I can use git diff and git apply to resolve the issue .\n"
        f"3. I need you to solve this issue by generating a single patch file that I can apply directly to this repository using git apply.\n"
        f"4. use the format as : {PATCH_FORMAT}"
    )

    requirement, system_messages, cleaned_user_message, issues_and_code = _prepare(inputs)
    return requirement, system_messages, cleaned_user_message, issues_and_code, prompt


@handle_exception(exception_type=Exception)
@retry(wait=wait_random_exponential(min=30, max=600), stop=stop_after_attempt(5))
async def run_agent(inputs, agent, **kwargs):
    script_names = kwargs.get("script_names", [])
    instance_id = kwargs.get("instance_id", "")
    locating_mode = kwargs.get("locating_mode")
    requirement, system_messages, cleaned_user_message, issues_and_code, prompt = construct_prompt(inputs, script_names)
    system_messages = system_messages.replace(" ", "")
    cleaned_user_message = cleaned_user_message.replace(" ", "")

    # locating ranges by using llm or retrieve mode
    logger.info("Start locating ranges...")
    if locating_mode:
        ranges = await locating_ranges(agent, instance_id, issues_and_code, locating_mode, script_names)
        ranges_content = f"\nThe locating range of code to be modified in file is: '''\n{str(ranges)}'''\n"
        logger.info(ranges_content)
        await agent.run([requirement, system_messages, "\n".join(issues_and_code), ranges_content, prompt])
    else:
        await agent.run([requirement, system_messages, "\n".join(issues_and_code), prompt])
    return agent.get_last_cell_source()


async def run_instance(instance, use_reflection=True, **kwargs):
    ga = GitAgent(use_reflection=use_reflection)
    script_names = extract_scripts_from_codetext(instance["text"])
    ga.script_names = script_names

    patch, repo, repo_path = reset_task_env(instance)
    if repo_path is None:
        return

    response = await run_agent(
        f"{instance['text']}\n\n", agent=ga, script_names=script_names, instance_id=instance["instance_id"], **kwargs
    )
    logger.info(f"Final response: {response}")
    save_history(ga)
    return response


async def locating_ranges(agent, instance_id, issues_and_code, locating_mode, script_names):
    # get locating ranges by llm
    if locating_mode == "llm":
        ranges = await locating_ranges_by_llm(agent, issues_and_code, script_names)
    # get locating ranges by retrieve
    elif locating_mode in ["jaccard", "bm25"]:
        ranges = await locating_ranges_by_retrieve(locating_mode, instance_id, issues_and_code)
    else:
        ranges = None
    return ranges


async def locating_ranges_by_retrieve(locating_mode, instance_id, issues_and_code):
    # read symbol changes file
    with open(SYMBOL_CHANGES_FILE, "r") as f:
        symbol_changes_list = json.load(f)
    sc_value = []
    for sc in symbol_changes_list:
        sc_value = sc.get(instance_id, [])
        if not sc_value:
            continue
        break
    # If there are n files, ranges contain n code snippets
    ranges = []
    # retrieve code snippets by jaccard
    if "jaccard" == locating_mode:
        for i in range(len(sc_value)):
            # retrieve code snippets by jaccard
            retrieved_codes = jaccard_retriever(
                code=issues_and_code[0],
                candidates=sc_value[i],
            )
            ranges.append(sc_value[i][retrieved_codes[0]] if sc_value and retrieved_codes else "")

        ranges_list = []
        for function_file in ranges:
            function_name = function_file.split(".")[-1]
            # extract code snippets based on function name
            pattern = r"(\d*\s*def\s+{function_name}\s*\(.*?\)\s*:\s*.*?)def".format(
                function_name=re.escape(function_name)
            )
            match = re.search(pattern, issues_and_code[1], re.DOTALL)
            content = match.group(1).strip() if match else ""
            if content:
                ranges_list.append(f"--- {function_file}\n{content}")
        ranges = "\n".join(ranges_list)
    # retrieve code snippets by bm25
    elif "bm25" == locating_mode:
        pass
    return ranges


async def locating_ranges_by_llm(agent, issues_and_code, script_names):
    # ranges_rsp is a dict, key and value are filename and lines scope respectively
    ranges_rsp = await locating_lines(agent, script_names, "\n".join(issues_and_code))
    # split code based on filename and lines
    codes = []
    for key, values in ranges_rsp.items():
        pattern = r"\[start of {file}\](.*?)\[end of {file}\]".format(file=re.escape(key))
        match = re.search(pattern, issues_and_code[1], re.DOTALL)
        content = match.group(1).strip() if match else ""
        code_snippets = []
        # extract code snippets based on lines scope
        for value in values:
            start, end = tuple(int(x) for x in value.split("-"))
            pattern = re.compile(r"^(?:.*\n){%d}(.*(?:\n.*?){%d})" % (start, end - start + 1), re.MULTILINE)
            match = pattern.search(content)
            snippet = match.group(1) if match else ""
            code_snippets.append(snippet)
        code_snippets = "\n".join(code_snippets)
        codes.append(f"--- {key}\n{code_snippets}")
    ranges = "\n".join(codes)
    return ranges


async def locating_lines(agent, script_names, issues_and_codes):
    max_retries = 3
    retries = 0
    lines = {}

    # retry 3 times if locating lines failed
    while retries < max_retries:
        try:
            prompt = LOCATING_LINE_RANGES_REQUIREMENT.format(
                script_names=script_names, issues_and_codes=issues_and_codes
            )
            lines_rsp = await agent.llm.aask(prompt)
            # parse lines dict
            lines = eval(CodeParser.parse_code(block="", text=lines_rsp))
            break
        except (ValueError, SyntaxError) as e:
            retries += 1
            if retries == max_retries:
                logger.error(f"Locating lines failed: {e}")
                raise e
            else:
                await asyncio.sleep(2**retries)

    return lines

# -*- coding: utf-8 -*-
# @Author  : stellahong (stellahong@fuzhi.ai)
# @Desc    :
import re

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.logs import logger
from metagpt.utils.exceptions import handle_exception
from metagpt.utils.recovery_util import save_history
from swe_bench.gitagent import GitAgent
from swe_bench.make_datasets.make_dataset import reset_task_env
from swe_bench.utils.utils import extract_scripts_from_codetext

PATCH_FORMAT = """
```diff
--- original_file.py
+++ modified_file.py
@@ -line_number,context_lines +line_number,context_lines @@
- original line of code to be replaced or removed
+ new line of code to be added or to replace the original
```
"""


def _prepare(inputs):
    requirement = "Please rewrite the code to address the issues. "
    system_messages = inputs.split("\n", 1)[0]
    user_message = inputs.split("\n", 1)[1]
    cleaned_user_message = re.sub("<patch>.*?</patch>", "", user_message, flags=re.DOTALL)

    issues = re.findall("<issue>(.*?)</issue>", user_message, flags=re.DOTALL)
    issues = [re.sub(r"#{3,4} Versions.*?(?=#{3,4}|\Z)", "", issues[0], flags=re.DOTALL)]
    traceback = re.findall(r"#{3,4} Actual Results.*", issues[0], flags=re.DOTALL)
    issues = traceback if traceback else issues
    code = re.findall("<code>(.*?)</code>", user_message, flags=re.DOTALL)

    return requirement, system_messages, cleaned_user_message, issues, code


def construct_prompt(inputs, script_names):
    prompt = (
        f"You only need to modify the code file listed here {script_names}."
        f"Notice: "
        f"1. Analysis the issue, especially for the ValueError, and identify influence code lines.\n"
        f"2. Only change a few lines, and make sure I can use git diff and git apply to resolve the issue .\n"
        f"3. I need you to solve this issue by generating a single patch file that I can apply directly to this repository using git apply.\n"
        f"4. use the format as : {PATCH_FORMAT}"
    )

    requirement, system_messages, cleaned_user_message, issues, code = _prepare(inputs)
    return requirement, system_messages, cleaned_user_message, issues, code, prompt


@handle_exception(exception_type=Exception)
@retry(wait=wait_random_exponential(min=30, max=600), stop=stop_after_attempt(5))
async def run_agent(inputs, agent, **kwargs):
    script_names = kwargs.get("script_names", [])
    requirement, system_messages, cleaned_user_message, issues, code, prompt = construct_prompt(inputs, script_names)
    system_messages = system_messages.replace(" ", "")
    cleaned_user_message = cleaned_user_message.replace(" ", "")
    issue_and_code = f"<issue>\n{issues[0]}\n</issue>\n\n<code>\n{code[0]}\n</code>"
    await agent.identify_line_ranges(issue_and_code)

    if kwargs.get("mode") == "test":
        return
    await agent.run([requirement, system_messages, cleaned_user_message, prompt])
    return agent.get_last_cell_source()


async def run_instance(instance, use_reflection=True, **kwargs):
    ga = GitAgent(use_reflection=use_reflection)
    script_names = extract_scripts_from_codetext(instance["text"])
    ga.script_names = script_names

    patch, repo, repo_path = reset_task_env(instance)
    if repo_path is None:
        return

    response = await run_agent(f"{instance['text']}\n\n", agent=ga, script_names=script_names, **kwargs)
    logger.info(f"Final response: {response}")
    save_history(ga)
    return response

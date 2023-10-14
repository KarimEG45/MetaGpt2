import json
import os

import pytest

from metagpt.logs import logger
from metagpt.const import WORKSPACE_ROOT
from examples.werewolf_game.schema import RoleExperience
from examples.werewolf_game.actions.experience_operation import AddNewExperiences, RetrieveExperiences


class TestExperiencesOperation:

    test_round_id = "test_01"
    samples_to_add = [
        RoleExperience(profile="Witch", reflection="The game is intense with two players claiming to be the Witch and one claiming to be the Seer. Player4's behavior is suspicious.", response="", outcome="", round_id=test_round_id),
        RoleExperience(profile="Witch", reflection="The game is in a critical state with only three players left, and I need to make a wise decision to save Player7 or not.", response="", outcome="", round_id=test_round_id),
        RoleExperience(profile="Seer", reflection="Player1, who is a werewolf, falsely claimed to be a Seer, and Player6, who might be a Witch, sided with him. I, as the real Seer, am under suspicion.", response="", outcome="", round_id=test_round_id),
    ]

    @pytest.mark.asyncio
    async def test_add(self):
        saved_file = f"{WORKSPACE_ROOT}/werewolf_game/experiences/{self.test_round_id}.json"
        if os.path.exists(saved_file):
            os.remove(saved_file)

        action = AddNewExperiences(collection_name="test", delete_existing=True)
        action.run(self.samples_to_add)
        
        # test insertion
        inserted = action.collection.get()
        assert len(inserted["documents"]) == len(self.samples_to_add)

        # test if we record the samples correctly to local file
        # & test if we could recover a embedding db from the file
        action = AddNewExperiences(collection_name="test", delete_existing=True)
        action.add_from_file(saved_file)
        inserted = action.collection.get()
        assert len(inserted["documents"]) == len(self.samples_to_add)

    @pytest.mark.asyncio
    async def test_retrieve(self):
        action = RetrieveExperiences(collection_name="test")

        query = "one player claimed to be Seer and the other Witch"
        results = action.run(query, "Witch")
        results = json.loads(results)

        assert len(results) == 2
        assert "The game is intense with two players" in results[0]
    
    @pytest.mark.asyncio
    async def test_check_experience_pool(self):
        logger.info("check experience pool")
        action = RetrieveExperiences(collection_name="role_reflection")
        print(*action.collection.get()["metadatas"][-5:], sep="\n")

    @pytest.mark.asyncio
    async def test_retrieve_werewolf_experience(self):
        
        action = RetrieveExperiences(collection_name="role_reflection")

        query = "there are conflicts"

        logger.info(f"test retrieval with {query=}")
        results = action.run(query, "Werewolf")
    
    @pytest.mark.asyncio
    async def test_retrieve_villager_experience(self):
        
        action = RetrieveExperiences(collection_name="role_reflection")

        query = "there are conflicts"

        logger.info(f"test retrieval with {query=}")
        results = action.run(query, "Seer")

// Included in wild_encounter.c (needs the generated ENCOUNTER_CHANCE_* macros and gWildMonHeaders).
// Requires a "zombie_mons" field in wild_encounters.json (6 slots, see PATCHES.md).

u32 ChooseWildMonIndex_Zombie(void)
{
    u8 rand = Random() % ENCOUNTER_CHANCE_ZOMBIE_MONS_TOTAL;

    if (rand < ENCOUNTER_CHANCE_ZOMBIE_MONS_SLOT_0)
        return 0;
    if (rand < ENCOUNTER_CHANCE_ZOMBIE_MONS_SLOT_1)
        return 1;
    if (rand < ENCOUNTER_CHANCE_ZOMBIE_MONS_SLOT_2)
        return 2;
    if (rand < ENCOUNTER_CHANCE_ZOMBIE_MONS_SLOT_3)
        return 3;
    if (rand < ENCOUNTER_CHANCE_ZOMBIE_MONS_SLOT_4)
        return 4;
    return 5;
}

const struct WildPokemonInfo *GetCurrentMapZombieMonsInfo(void)
{
    u16 headerId = GetCurrentMapWildMonHeaderId();
    enum TimeOfDay timeOfDay;

    if (headerId == HEADER_NONE)
        return NULL;
    timeOfDay = GetTimeOfDayForEncounters(headerId, WILD_AREA_LAND);
    return gWildMonHeaders[headerId].encounterTypes[timeOfDay].zombieMonsInfo;
}

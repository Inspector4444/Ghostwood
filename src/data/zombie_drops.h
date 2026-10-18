struct ZombieDrop
{
    u16 item;
    u16 weight;
};

struct ZombieDropPool
{
    u16 map;            // MAP_xxx, or MAP_UNDEFINED for the default pool
    u16 noDropWeight;   // weight of "nothing" - this is the per-area drop chance
    u8  maxPerBattle;   // cap on drops per battle in this area, 0 = no cap
    u8  count;
    const struct ZombieDrop *drops;
};

static const struct ZombieDrop sDefaultDrops[] =
{
    { ITEM_POTION,  50 },
    { ITEM_ANTIDOTE, 30 },
    { ITEM_NUGGET,   5 },
};

static const struct ZombieDrop sRoute101Drops[] =
{
    { ITEM_POTION,   60 },
    { ITEM_POKE_BALL, 40 },
};

static const struct ZombieDropPool sZombieDropPools[] =
{
    { MAP_ROUTE101, 70, 1, ARRAY_COUNT(sRoute101Drops), sRoute101Drops },
    // default pool must stay last
    { MAP_UNDEFINED, 75, 2, ARRAY_COUNT(sDefaultDrops), sDefaultDrops },
};

static const struct ZombieDropPool *GetDropPool(void)
{
    u32 i;
    u16 cur = (gSaveBlock1Ptr->location.mapGroup << 8) | gSaveBlock1Ptr->location.mapNum;

    for (i = 0; i < ARRAY_COUNT(sZombieDropPools) - 1; i++)
    {
        if (sZombieDropPools[i].map == cur)
            return &sZombieDropPools[i];
    }
    return &sZombieDropPools[ARRAY_COUNT(sZombieDropPools) - 1];
}

static void RollDrop(const struct ZombieDropPool *pool)
{
    u32 total = pool->noDropWeight, roll, i;

    if (sPendingDropCount >= ARRAY_COUNT(sPendingDrops)
     || (pool->maxPerBattle && sPendingDropCount >= pool->maxPerBattle))
        return;

    for (i = 0; i < pool->count; i++)
        total += pool->drops[i].weight;
    if (total == 0)
        return;

    roll = Random() % total;
    if (roll < pool->noDropWeight)
        return; // rolled "nothing"
    roll -= pool->noDropWeight;

    for (i = 0; i < pool->count; i++)
    {
        if (roll < pool->drops[i].weight)
        {
            sPendingDrops[sPendingDropCount++].item = pool->drops[i].item;
            return;
        }
        roll -= pool->drops[i].weight;
    }
}
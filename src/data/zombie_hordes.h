// Which maps have zombie hordes. The mon lists themselves live in
// wild_encounters.json under "zombie_mons" (same format as land_mons).

// Placeholder sprites; swap for dedicated zombie graphics when they exist.
struct ZombieLook
{
    u16 gfxId;     // overworld sprite
    u16 trainerA;  // used when this zombie is the first opponent
    u16 trainerB;  // used when it joins as the second opponent
};

static const struct ZombieLook sZombieLooks[] =
{
    { OBJ_EVENT_GFX_ZOMBIEMAN,   TRAINER_ZOMBIE_A,   TRAINER_ZOMBIE_B },
    { OBJ_EVENT_GFX_WOMAN_1, TRAINER_ZOMBIE_2A, TRAINER_ZOMBIE_2B },
    // { OBJ_EVENT_GFX_YOUNGSTER,   TRAINER_ZOMBIE_BOY_A,   TRAINER_ZOMBIE_BOY_B },
    // { OBJ_EVENT_GFX_COOK,   TRAINER_ZOMBIE_COOK_A,   TRAINER_ZOMBIE_COOK_B },
};

static const struct ZombieArea sZombieAreas[] =
{
    { MAP_GROUP(MAP_ROUTE101), MAP_NUM(MAP_ROUTE101), 4, 1, 2, 0 },
    { MAP_GROUP(MAP_ROUTE102), MAP_NUM(MAP_ROUTE102), 5, 1, 3, 0 },
    { MAP_GROUP(MAP_ROUTE103), MAP_NUM(MAP_ROUTE103), 5, 2, 3, ZOMBIE_AREA_ALLOW_WATER },
    { MAP_GROUP(MAP_ROUTE401), MAP_NUM(MAP_ROUTE401), 4, 1, 2, 0 },
};

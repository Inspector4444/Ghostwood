// weight = relative chance among drops
struct ZombieDrop
{
    u16 item;
    u8 weight;
};

static const struct ZombieDrop sZombieDrops[] =
{
    { ITEM_NUGGET,        10 },
    { ITEM_ANTIDOTE,      40 },
    { ITEM_POTION,        30 },
    { ITEM_REVIVE,         5 },
    { ITEM_BIG_NUGGET,     1 },
};
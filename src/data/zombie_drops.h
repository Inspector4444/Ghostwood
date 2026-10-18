// weight = relative chance among drops; quantity is rolled in [minQty, maxQty]
struct ZombieDrop
{
    u16 item;
    u8 weight;
    u8 minQty;
    u8 maxQty;
};

static const struct ZombieDrop sZombieDrops[] =
{
    { ITEM_NUGGET,        10, 1, 1 },
    { ITEM_ANTIDOTE,      40, 1, 2 },
    { ITEM_POTION,        30, 1, 1 },
    { ITEM_REVIVE,         5, 1, 1 },
    { ITEM_BIG_NUGGET,     1, 1, 1 },
};
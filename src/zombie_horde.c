#include "global.h"
#include "event_object_movement.h"
#include "field_control_avatar.h"
#include "field_player_avatar.h"
#include "fieldmap.h"
#include "metatile_behavior.h"
#include "overworld.h"
#include "random.h"
#include "script.h"
#include "sprite.h"
#include "event_scripts.h"
#include "wild_encounter.h"
#include "zombie_battle.h"
#include "zombie_flow.h"
#include "zombie_horde.h"
#include "constants/event_objects.h"
#include "constants/event_object_movement.h"
#include "constants/maps.h"
#include "constants/items.h"
#include "data/zombie_hordes.h"

struct ZombieState
{
    bool8 aggro;
    bool8 defeated;
    bool8 despawning;
    u16 despawnTimer;
};

static EWRAM_DATA struct ZombieState sZombie[ZOMBIE_LOCALID_COUNT] = {0};
static EWRAM_DATA const struct ZombieArea *sArea = NULL;
static EWRAM_DATA s16 sLastPlayerX = 0;
static EWRAM_DATA s16 sLastPlayerY = 0;
static EWRAM_DATA u16 sSpawnTimer = 0;
static EWRAM_DATA u8 sLastMapGroup = 0;
static EWRAM_DATA u8 sLastMapNum = 0;
static EWRAM_DATA bool8 sMapKnown = FALSE;
static EWRAM_DATA u16 sGraceTimer = 0;

static struct ZombieState *GetState(const struct ObjectEvent *z);

static const u8 sDirList[4] = {DIR_SOUTH, DIR_NORTH, DIR_WEST, DIR_EAST};

bool8 IsZombieObjectEvent(const struct ObjectEvent *objectEvent)
{
    return objectEvent->active && objectEvent->movementType == MOVEMENT_TYPE_ZOMBIE;
}

void ZombieHorde_MarkDefeated(struct ObjectEvent *z)
{
    GetState(z)->defeated = TRUE;
}

bool8 ZombieHorde_IsDefeated(struct ObjectEvent *z)
{
    return GetState(z)->defeated;
}

bool8 ZombieHorde_IsAggro(struct ObjectEvent *z)
{
    return GetState(z)->aggro;
}

const struct ZombieArea *ZombieHorde_GetCurrentArea(void)
{
    u32 i;
    for (i = 0; i < ARRAY_COUNT(sZombieAreas); i++)
    {
        if (sZombieAreas[i].mapGroup == gSaveBlock1Ptr->location.mapGroup
         && sZombieAreas[i].mapNum == gSaveBlock1Ptr->location.mapNum)
            return &sZombieAreas[i];
    }
    return NULL;
}

static struct ZombieState *GetState(const struct ObjectEvent *z)
{
    u32 slot = z->localId - ZOMBIE_LOCALID_BASE;
    if (slot >= ZOMBIE_LOCALID_COUNT)
        return &sZombie[0]; // should never happen
    return &sZombie[slot];
}

static void StartDespawn(struct ObjectEvent *z)
{
    struct ZombieState *st = GetState(z);
    if (st->despawning)
        return;
    st->despawning = TRUE;
    st->despawnTimer = 0;
}

static u32 GetZombieDistance(s16 x1, s16 y1, s16 x2, s16 y2)
{
    s32 dx = x1 > x2 ? x1 - x2 : x2 - x1;
    s32 dy = y1 > y2 ? y1 - y2 : y2 - y1;

	#ifdef ZOMBIE_DIST_MANHATTAN
		return dx + dy;
	#else
		return dx > dy ? dx : dy;
	#endif
}

static struct ObjectEvent *GetPlayerObject(void)
{
    return &gObjectEvents[gPlayerAvatar.objectEventId];
}

static bool8 IsTileOccupied(s16 x, s16 y)
{
    u32 i;

    // Loaded objects (including the player): where they are and where they came from
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
    {
        struct ObjectEvent *o = &gObjectEvents[i];
        if (!o->active)
            continue;
        if ((o->currentCoords.x == x && o->currentCoords.y == y)
         || (o->previousCoords.x == x && o->previousCoords.y == y))
            return TRUE;
    }
    // Map-defined NPCs that exist but are currently culled off-screen
    for (i = 0; i < OBJECT_EVENT_TEMPLATES_COUNT; i++)
    {
        const struct ObjectEventTemplate *t = &gSaveBlock1Ptr->objectEventTemplates[i];
        if (t->localId == 0)
            continue;
        if (t->x + MAP_OFFSET == x && t->y + MAP_OFFSET == y)
            return TRUE;
    }
    return FALSE;
}

static bool8 IsInsideCurrentMap(s16 x, s16 y)
{
    return x >= MAP_OFFSET && y >= MAP_OFFSET
        && x < gMapHeader.mapLayout->width + MAP_OFFSET
        && y < gMapHeader.mapLayout->height + MAP_OFFSET;
}

// ---- terrain rules (stub: per-route flags hook in here) ----
static bool8 IsTileWalkable(s16 x, s16 y)
{
    if (!IsInsideCurrentMap(x, y))
        return FALSE;
    if (MapGridGetCollisionAt(x, y) != 0)
        return FALSE;
    if (!(sArea && (sArea->flags & ZOMBIE_AREA_ALLOW_WATER))
     && MetatileBehavior_IsSurfableWaterOrUnderwater(MapGridGetMetatileBehaviorAt(x, y)))
        return FALSE;
    return TRUE;
}

bool8 ZombieHorde_CanStep(struct ObjectEvent *z, u8 dir)
{
    s16 x = z->currentCoords.x, y = z->currentCoords.y;
    switch (dir)
    {
    case DIR_SOUTH: y++; break;
    case DIR_NORTH: y--; break;
    case DIR_WEST:  x--; break;
    case DIR_EAST:  x++; break;
    }
    return IsInsideCurrentMap(x, y);
}

// Returns the 2-tile jump action if stepping `dir` is a ledge hop with a free landing,
// otherwise MOVEMENT_ACTION_NONE.
u8 ZombieHorde_GetHopAction(struct ObjectEvent *z, u8 dir)
{
    s16 x = z->currentCoords.x, y = z->currentCoords.y;

    MoveCoords(dir, &x, &y);   // the ledge tile
    if (GetLedgeJumpDirection(x, y, dir) != dir)
        return MOVEMENT_ACTION_NONE;
    MoveCoords(dir, &x, &y);   // the landing tile
    if (!IsTileWalkable(x, y) || IsTileOccupied(x, y))
        return MOVEMENT_ACTION_NONE;
    return GetJump2MovementAction(dir);
}

static bool8 HasLineOfSight(s16 zx, s16 zy, s16 px, s16 py)
{
    s16 x = zx, y = zy;
    s16 sx = (px > zx) - (px < zx);
    s16 sy = (py > zy) - (py < zy);

    if (zx != px && zy != py)
        return FALSE;
    if (GetZombieDistance(zx, zy, px, py) > ZOMBIE_SIGHT_RANGE)
        return FALSE;
    for (;;)
    {
        x += sx;
        y += sy;
        if (x == px && y == py)
            return TRUE;
        if (!IsTileWalkable(x, y) || IsTileOccupied(x, y))
            return FALSE;
    }
}

static void AddDir(u8 dirs[5], u32 *n, u8 dir)
{
    u32 i;
    if (dir == DIR_NONE)
        return;
    for (i = 0; i < *n; i++)
        if (dirs[i] == dir)
            return;
    dirs[(*n)++] = dir;
}

static u8 OppositeDir(u8 d)
{
    switch (d)
    {
    case DIR_SOUTH: return DIR_NORTH;
    case DIR_NORTH: return DIR_SOUTH;
    case DIR_WEST:  return DIR_EAST;
    case DIR_EAST:  return DIR_WEST;
    }
    return DIR_NONE;
}

u8 ZombieHorde_Think(struct ObjectEvent *z, u8 dirs[5])
{
    struct ObjectEvent *player = GetPlayerObject();
    struct ZombieState *st = GetState(z);
    s16 zx = z->currentCoords.x, zy = z->currentCoords.y;
    s16 px = player->currentCoords.x, py = player->currentCoords.y;
    u32 n = 0, d = GetZombieDistance(zx, zy, px, py), i, start;
    u8 mode = ZOMBIE_THINK_WANDER;

    if (st->defeated || st->despawning)
    {
        dirs[0] = DIR_NONE;
        return ZOMBIE_THINK_CHASE;
    }
    if (sGraceTimer)
        st->aggro = FALSE;
    if (!st->aggro && sGraceTimer == 0)
    {
        if (d <= ZOMBIE_AGGRO_RADIUS || HasLineOfSight(zx, zy, px, py))
        {
            st->aggro = TRUE;
            mode = ZOMBIE_THINK_ALERT;
        }
    }
    else if (d > ZOMBIE_LOSE_INTEREST_DIST)
    {
        st->aggro = FALSE;
    }
    else
    {
        mode = ZOMBIE_THINK_CHASE;
    }

    if (st->aggro)
    {
        u8 xDir = px > zx ? DIR_EAST : (px < zx ? DIR_WEST : DIR_NONE);
        u8 yDir = py > zy ? DIR_SOUTH : (py < zy ? DIR_NORTH : DIR_NONE);

        if (mode == ZOMBIE_THINK_ALERT)
        {
            // just face the player for the "!"
            AddDir(dirs, &n, xDir != DIR_NONE ? xDir : yDir);
        }
        else if (ZombieFlow_IsInside(zx, zy))
        {
            u8 flow[4];
            u8 rev = OppositeDir(z->movementDirection);
            u32 cnt = ZombieFlow_GetDirections(zx, zy, z->localId, flow);

            for (i = 0; i < cnt; i++)       // forward and sideways first
                if (flow[i] != rev)
                    AddDir(dirs, &n, flow[i]);
            for (i = 0; i < cnt; i++)       // undoing the last step only as a last resort
                if (flow[i] == rev)
                    AddDir(dirs, &n, flow[i]);
        }
        else
        {
            // outside the pathing grid: head straight for the player
            AddDir(dirs, &n, xDir);
            AddDir(dirs, &n, yDir);
        }
    }
    else
    {
        // wandering: random order
        start = Random() & 3;
        for (i = 0; i < 4; i++)
            AddDir(dirs, &n, sDirList[(start + i) & 3]);
    }
    dirs[n] = DIR_NONE;
    return mode;
}

// ---- spawning ----
static u32 CountZombies(void)
{
    u32 i, n = 0;
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
        if (IsZombieObjectEvent(&gObjectEvents[i]))
            n++;
    return n;
}

static s32 FindFreeLocalId(void)
{
    u32 slot, i;
    for (slot = 0; slot < ZOMBIE_LOCALID_COUNT; slot++)
    {
        bool8 used = FALSE;
        for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
            if (gObjectEvents[i].active && IsZombieObjectEvent(&gObjectEvents[i]) && gObjectEvents[i].localId == ZOMBIE_LOCALID_BASE + slot)
                used = TRUE;
        if (!used)
            return ZOMBIE_LOCALID_BASE + slot;
    }
    return -1;
}

void ZombieHorde_GetTrainerIds(const struct ObjectEvent *z, u16 *outA, u16 *outB)
{
    u32 i;
    for (i = 0; i < ARRAY_COUNT(sZombieLooks); i++)
    {
        if (sZombieLooks[i].gfxId == z->graphicsId)
        {
            *outA = sZombieLooks[i].trainerA;
            *outB = sZombieLooks[i].trainerB;
            return;
        }
    }
    *outA = sZombieLooks[0].trainerA; // fallback
    *outB = sZombieLooks[0].trainerB;
}

static void TrySpawnZombie(void)
{
    struct ObjectEvent *player = GetPlayerObject();
    u32 tries;
    s32 localId = FindFreeLocalId();
    u8 maxActive = sArea->maxActive ? sArea->maxActive : ZOMBIE_MAX_ACTIVE;

    if (localId < 0 || CountZombies() >= maxActive)
        return;
    for (tries = 0; tries < ZOMBIE_SPAWN_TRIES; tries++)
    {
        s32 range = ZOMBIE_SPAWN_DIST_MAX - ZOMBIE_SPAWN_DIST_MIN + 1;
        s32 dx = ZOMBIE_SPAWN_DIST_MIN + Random() % range;
        s32 dy = (s32)(Random() % (ZOMBIE_SPAWN_DIST_MAX * 2 + 1)) - ZOMBIE_SPAWN_DIST_MAX;
        s16 x, y;
        u8 id;

        if (Random() & 1)
            dx = -dx;
        if (Random() & 1) // use the vertical ring instead: swap axes
        {
            s32 t = dx; dx = dy; dy = t;
        }
        x = player->currentCoords.x + dx;
        y = player->currentCoords.y + dy;
        if (GetZombieDistance(x, y, player->currentCoords.x, player->currentCoords.y) < ZOMBIE_SPAWN_DIST_MIN)
            continue;
        if (!IsTileWalkable(x, y) || IsTileOccupied(x, y) || GetObjectEventIdByXY(x, y) != OBJECT_EVENTS_COUNT)
            continue;
        id = SpawnSpecialObjectEventParameterized(sZombieLooks[Random() % ARRAY_COUNT(sZombieLooks)].gfxId,
                                                  MOVEMENT_TYPE_ZOMBIE, localId, x, y, MapGridGetElevationAt(x, y));
        if (id < OBJECT_EVENTS_COUNT)
        {
            struct ZombieState *st = GetState(&gObjectEvents[id]);
            st->aggro = FALSE;
            st->defeated = FALSE;
            st->despawning = FALSE;
            st->despawnTimer = 0;
        }
        return;
    }
}

// Fades every zombie out (used on map change, e.g. crossing a connection)
void ZombieHorde_RemoveAll(void)
{
    u32 i;
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
        if (IsZombieObjectEvent(&gObjectEvents[i]))
            StartDespawn(&gObjectEvents[i]);
}

// ---- contact ----
void ZombieHorde_OnContact(struct ObjectEvent *z)
{
    if (ZombieHorde_IsDefeated(z) || GetState(z)->despawning)
        return;
    if (sGraceTimer)
        return;
    if (ZombieBattle_IsPending())
    {
        ZombieBattle_AddSecondZombie(z); // transition still running: becomes a double battle
        return;
    }
    if (ArePlayerFieldControlsLocked())
        return;
    ZombieBattle_Register(z);
    ScriptContext_SetupScript(Ghostwood_EventScript_ZombieBattle);
}

static void CheckContacts(void)
{
    struct ObjectEvent *player = GetPlayerObject();
    struct Sprite *ps = &gSprites[player->spriteId];
    u32 i;
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
    {
        struct ObjectEvent *z = &gObjectEvents[i];
        struct Sprite *zs;
        s32 dx, dy;

        if (!IsZombieObjectEvent(z) || ZombieBattle_IsRegistered(z) || ZombieHorde_IsDefeated(z) || GetState(z)->despawning)
            continue;
        // cheap tile prefilter (coords are step destinations, so allow slack)
        if (GetZombieDistance(z->currentCoords.x, z->currentCoords.y, player->currentCoords.x, player->currentCoords.y) > 2)
            continue;
        zs = &gSprites[z->spriteId];
        dx = (zs->x + zs->x2) - (ps->x + ps->x2);
        dy = (zs->y + zs->y2) - (ps->y + ps->y2);
        if (dx < 0) dx = -dx;
        if (dy < 0) dy = -dy;
        if (dx + dy <= 16) // edge to edge: exactly one tile apart on screen
            ZombieHorde_OnContact(z);
    }
}

void ZombieHorde_StartGrace(void)
{
    u32 i;
    sGraceTimer = ZOMBIE_GRACE_FRAMES;
    for (i = 0; i < ZOMBIE_LOCALID_COUNT; i++)
        sZombie[i].aggro = FALSE;
}

// ---- despawn fade (dither: thins out the visible frames over time) ----
// Bayer-style order so the visible frames spread out instead of clumping
static const u8 sFadeOrder[8] = { 0, 4, 2, 6, 1, 5, 3, 7 };

// elapsed: frames since the fade began. Returns TRUE once fully faded.
static bool8 ZombieHorde_FadeStep(struct ObjectEvent *obj, u16 elapsed)
{
    u32 shown = 8 - (8 * elapsed) / ZOMBIE_FADE_FRAMES;   // 8..0 of every 8 frames visible

    obj->invisible = (sFadeOrder[elapsed & 7] >= shown);
    return elapsed >= ZOMBIE_FADE_FRAMES;
}

static void UpdateDespawns(void)
{
    u32 i;
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
    {
        struct ObjectEvent *z = &gObjectEvents[i];
        struct ZombieState *st;

        if (!IsZombieObjectEvent(z))
            continue;
        st = GetState(z);
        if (!st->despawning)
            continue;
        if (ZombieHorde_FadeStep(z, st->despawnTimer++))
        {
            st->despawning = FALSE;
            st->despawnTimer = 0;
            st->aggro = FALSE;
            st->defeated = FALSE;
            RemoveObjectEvent(z);
        }
    }
}

// ---- per-frame ----
void ZombieHorde_Update(void)
{
    struct ObjectEvent *player;
    u32 i;

    if (sGraceTimer)
        sGraceTimer--;
    UpdateDespawns(); // before any early return, so fades always finish

    if (!ZOMBIE_SYSTEM_ENABLED || gPlayerAvatar.objectEventId >= OBJECT_EVENTS_COUNT)
        return;

    // Map changed (warp, connection, save load): fade leftovers, refresh area
    if (!sMapKnown || gSaveBlock1Ptr->location.mapGroup != sLastMapGroup || gSaveBlock1Ptr->location.mapNum != sLastMapNum)
    {
        sMapKnown = TRUE;
        sLastMapGroup = gSaveBlock1Ptr->location.mapGroup;
        sLastMapNum = gSaveBlock1Ptr->location.mapNum;
        ZombieHorde_RemoveAll();
        ZombieBattle_Reset();
        sArea = ZombieHorde_GetCurrentArea();
        ZombieFlow_Invalidate();
        sSpawnTimer = ZOMBIE_SPAWN_INTERVAL_MIN;
        for (i = 0; i < ZOMBIE_LOCALID_COUNT; i++)
        {
            sZombie[i].aggro = FALSE;
            sZombie[i].defeated = FALSE;
        }
    }
    if (sArea == NULL)
        return;

    CheckContacts(); // runs during the battle transition too, so a 2nd zombie can join
    if (ZombieBattle_IsPending())
        return;
    if (ArePlayerFieldControlsLocked())
        return;

    player = GetPlayerObject();
    if (!ZombieFlow_IsInside(player->currentCoords.x, player->currentCoords.y)
     || player->currentCoords.x != sLastPlayerX || player->currentCoords.y != sLastPlayerY)
    {
        sLastPlayerX = player->currentCoords.x;
        sLastPlayerY = player->currentCoords.y;
        ZombieFlow_Build(sLastPlayerX, sLastPlayerY, IsTileWalkable);
    }

    // Far zombies fade out
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
    {
        struct ObjectEvent *z = &gObjectEvents[i];
        if (IsZombieObjectEvent(z)
         && GetZombieDistance(z->currentCoords.x, z->currentCoords.y, player->currentCoords.x, player->currentCoords.y) > ZOMBIE_DESPAWN_DIST)
            StartDespawn(z);
    }

    // like the OWE spawner: don't spawn while the player is mid step
    if (player->currentCoords.x != player->previousCoords.x || player->currentCoords.y != player->previousCoords.y)
        return;

    if (sSpawnTimer > 0)
    {
        sSpawnTimer--;
        return;
    }
    sSpawnTimer = ZOMBIE_SPAWN_INTERVAL_MIN + Random() % (ZOMBIE_SPAWN_INTERVAL_MAX - ZOMBIE_SPAWN_INTERVAL_MIN + 1);
    TrySpawnZombie();
}

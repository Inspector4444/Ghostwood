#include "global.h"
#include "battle.h"
#include "constants/battle.h"
#include "constants/items.h"
#include "event_data.h"
#include "event_object_movement.h"
#include "field_player_avatar.h"
#include "pokemon.h"
#include "random.h"
#include "script.h"
#include "task.h"
#include "wild_encounter.h"
#include "zombie_battle.h"
#include "zombie_horde.h"
#include "constants/trainers.h"

static EWRAM_DATA u8 sFleeAttempts = 0;
static EWRAM_DATA struct { u16 item; } sPendingDrops[2] = {0};
static EWRAM_DATA u8 sPendingDropCount = 0;

#include "data/zombie_drops.h"

enum
{
    ZB_IDLE,
    ZB_REGISTERED,  // contact happened, script about to run
    ZB_STARTED,     // battle task + transition running
    ZB_IN_BATTLE,   // parties built, battle running
};

static EWRAM_DATA struct
{
    u8 state;
    u8 count;
    u8 objectIds[2];
} sZB = {0};

static void FaceAndFreeze(struct ObjectEvent *z)
{
    enum Direction dir = DetermineObjectEventDirectionFromObject(&gObjectEvents[gPlayerAvatar.objectEventId], z);
    ObjectEventTurn(z, dir);   // sets facing and shows the standing frame for that direction
    FreezeObjectEvent(z);      // freeze after turning, so the frame stays
}

bool8 IsZombieBattle(void)
{
    return sZB.state == ZB_IN_BATTLE;
}

bool8 ZombieBattle_RollFlee(void)
{
    u32 chance = ZOMBIE_FLEE_BASE_PERCENT + ZOMBIE_FLEE_BONUS_PER_TRY * sFleeAttempts;
    sFleeAttempts++;
    return Random() % 100 < chance;
}

bool8 ZombieBattle_IsPending(void)
{
    return sZB.state != ZB_IDLE;
}

bool8 ZombieBattle_IsRegistered(struct ObjectEvent *z)
{
    u32 i;
    for (i = 0; sZB.state != ZB_IDLE && i < sZB.count; i++)
        if (&gObjectEvents[sZB.objectIds[i]] == z)
            return TRUE;
    return FALSE;
}

void ZombieBattle_Reset(void)
{
    sZB.state = ZB_IDLE;
    sZB.count = 0;
}

void ZombieBattle_Register(struct ObjectEvent *z)
{
    sZB.state = ZB_REGISTERED;
    sZB.count = 1;
    sZB.objectIds[0] = z - gObjectEvents;
	FaceAndFreeze(z);
}

void ZombieBattle_AddSecondZombie(struct ObjectEvent *z)
{
    // Only until the parties get built
    if (sZB.count >= 2 || sZB.state == ZB_IN_BATTLE || ZombieBattle_IsRegistered(z))
        return;
    sZB.objectIds[sZB.count++] = z - gObjectEvents;
    FaceAndFreeze(z);
}

void ZombieBattle_NextDrop(void)   // callnative: sets 0x8004 = item, 0x8005 = quantity
{
    if (sPendingDropCount == 0)
    {
        gSpecialVar_Result = FALSE;
        return;
    }
    sPendingDropCount--;
    gSpecialVar_0x8004 = sPendingDrops[sPendingDropCount].item;
    gSpecialVar_Result = TRUE;
}

void ZombieBattle_ScriptStart(void)
{
    u32 i;
    // Freeze the world except zombies, so a second zombie can still reach the player
    for (i = 0; i < OBJECT_EVENTS_COUNT; i++)
    {
        struct ObjectEvent *obj = &gObjectEvents[i];
        if (obj->active && !obj->isPlayer && (!IsZombieObjectEvent(obj) || ZombieBattle_IsRegistered(obj)))
            FreezeObjectEvent(obj);
    }
    StopPlayerAvatar();
    sZB.state = ZB_STARTED;
    BattleSetup_StartZombieBattle();
}

static const u8 sMonPercents[] = ZOMBIE_MON_PERCENTS;

// ---- party generation (wild-style: level range + species list from "zombie_mons") ----
static void BuildZombieParty(u8 partyId)
{
    const struct ZombieArea *area = ZombieHorde_GetCurrentArea();
    const struct WildPokemonInfo *info = GetCurrentMapZombieMonsInfo();
    u32 minMons = (area && area->minMons) ? area->minMons : ZOMBIE_MIN_MONS;
    u32 maxMons = (area && area->maxMons) ? area->maxMons : ZOMBIE_MAX_MONS;
    u32 count, i;

    if (maxMons < minMons)
        maxMons = minMons;
    if (maxMons > PARTY_SIZE)
        maxMons = PARTY_SIZE;
	
    count = 0;
    while (count < maxMons
        && (count < minMons || (count < ARRAY_COUNT(sMonPercents) && Random() % 100 < sMonPercents[count])))
        count++;
		
    for (i = 0; i < PARTY_SIZE; i++)
        ZeroMonData(&gParties[partyId][i]);

    for (i = 0; i < count; i++)
    {
        enum Species species = SPECIES_UNOWN; // fallback if the map has no zombie_mons table
        u8 level = 3;
        if (info != NULL)
        {
            u32 slot = ChooseWildMonIndex_Zombie();
            const struct WildPokemon *wp = &info->wildPokemon[slot];
            u8 lo = wp->minLevel <= wp->maxLevel ? wp->minLevel : wp->maxLevel;
            u8 hi = wp->minLevel <= wp->maxLevel ? wp->maxLevel : wp->minLevel;
            species = wp->species;
            level = lo + Random() % (hi - lo + 1);
        }
        CreateMonWithIVs(&gParties[partyId][i], species, level, Random32(), OTID_STRUCT_PLAYER_ID, USE_RANDOM_IVS);
        GiveMonInitialMoveset(&gParties[partyId][i]);
        // Mark "no gimmick" the same way trainer party data does, so the AI won't Dynamax/Tera them
        {
            u32 blockDynamax = BLOCK_AI_DYNAMAX;
            u32 noTera = TYPE_MYSTERY;
            SetMonData(&gParties[partyId][i], MON_DATA_DYNAMAX_LEVEL, &blockDynamax);
            SetMonData(&gParties[partyId][i], MON_DATA_TERA_TYPE, &noTera);
        }
    }
}

void ZombieBattle_OnTransitionDone(void)
{
    bool8 two;
    u16 a1, b1, a2 = 0, b2 = 0;

    if (sZB.state != ZB_STARTED)
        return;
    two = sZB.count >= 2;
    ZombieHorde_GetTrainerIds(&gObjectEvents[sZB.objectIds[0]], &a1, &b1);
    if (two)
        ZombieHorde_GetTrainerIds(&gObjectEvents[sZB.objectIds[1]], &a2, &b2);

    BattleSetup_FinalizeZombieBattle(two, a1, two ? b2 : 0);
    BuildZombieParty(B_TRAINER_OPPONENT_A);
    if (two)
        BuildZombieParty(B_TRAINER_OPPONENT_B);
    sFleeAttempts = 0;
    sZB.state = ZB_IN_BATTLE;
}

void ZombieBattle_Cleanup(void)
{
    u32 i;
	const struct ZombieDropPool *pool = GetDropPool();

    sPendingDropCount = 0;
    if (gBattleOutcome == B_OUTCOME_RAN)
    {
        ZombieHorde_StartGrace();
        ZombieBattle_Reset();
        gSpecialVar_Result = FALSE;
        return;
    }
    for (i = 0; i < sZB.count; i++)
    {
        if (IsZombieObjectEvent(&gObjectEvents[sZB.objectIds[i]]))
            RollDrop(pool);
    }
    gSpecialVar_Result = (sPendingDropCount > 0);
}

#define tTimer   data[0]
#define tLength  data[1]
#define tCount   data[2]
#define tId(i)   data[3 + (i)]

static void Task_ZombieFade(u8 taskId)
{
    s16 *data = gTasks[taskId].data;
    s32 i;

    tTimer++;
    for (i = 0; i < tCount; i++)
    {
        struct ObjectEvent *z = &gObjectEvents[tId(i)];
        if (IsZombieObjectEvent(z) && ZombieHorde_IsDefeated(z))
            z->invisible = ((tTimer * tTimer) / 24) & 1;   // blink gets faster
    }
    if (tTimer >= tLength)
    {
        for (i = 0; i < tCount; i++)
        {
            struct ObjectEvent *z = &gObjectEvents[tId(i)];
            if (IsZombieObjectEvent(z) && ZombieHorde_IsDefeated(z))
                RemoveObjectEvent(z);
        }
        DestroyTask(taskId);
    }
}

// Starts the fade in the background and frees the battle state immediately.
void ZombieBattle_BeginFade(void)
{
    u8 taskId = CreateTask(Task_ZombieFade, 80);
    s16 *data = gTasks[taskId].data;
    u32 i;

    tTimer = 0;
    tLength = ZOMBIE_FADE_FRAMES;
    tCount = 0;
    if (sZB.state != ZB_IDLE)       // after a successful flee, sZB was already reset: nothing to fade
    {
        for (i = 0; i < sZB.count; i++)
        {
            struct ObjectEvent *z = &gObjectEvents[sZB.objectIds[i]];
            if (!IsZombieObjectEvent(z))
                continue;
            ZombieHorde_MarkDefeated(z);
            tId(tCount) = sZB.objectIds[i];
            tCount++;
        }
    }
    ZombieBattle_Reset();
}

#undef tTimer
#undef tLength
#undef tCount
#undef tId
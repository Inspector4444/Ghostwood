#ifndef GUARD_ZOMBIE_HORDE_H
#define GUARD_ZOMBIE_HORDE_H

#include "config/zombie.h"

// Per-area flags (stubs - the terrain rules are meant to grow per route)
#define ZOMBIE_AREA_ALLOW_WATER   (1 << 0) // zombies may path through surfable water
#define ZOMBIE_AREA_STUB_1        (1 << 1) // reserved for future terrain rules
#define ZOMBIE_AREA_STUB_2        (1 << 2)

struct ZombieArea
{
    u16 mapGroup;
    u16 mapNum;
    u8 maxActive;   // 0 = ZOMBIE_MAX_ACTIVE
    u8 minMons;     // 0 = ZOMBIE_MIN_MONS
    u8 maxMons;     // 0 = ZOMBIE_MAX_MONS
    u16 flags;
};

// Decisions returned to the movement type
enum ZombieThinkMode
{
    ZOMBIE_THINK_WANDER,
    ZOMBIE_THINK_ALERT,   // just noticed the player: play "!" then chase
    ZOMBIE_THINK_CHASE,
};

void ZombieHorde_GetTrainerIds(const struct ObjectEvent *objectEvent, u16 *idA, u16 *idB);

// Call once per frame while the overworld runs (also during the battle transition).
void ZombieHorde_Update(void);
void ZombieHorde_StartGrace(void);

void ZombieHorde_MarkDefeated(struct ObjectEvent *zombie);
bool8 ZombieHorde_IsDefeated(struct ObjectEvent *zombie);

// Used by the zombie movement type (event_object_movement.c).
// dirs[] is filled with candidate directions, best first, terminated by DIR_NONE.
u8 ZombieHorde_Think(struct ObjectEvent *zombie, u8 dirs[5]);
u8 ZombieHorde_GetHopAction(struct ObjectEvent *z, u8 dir);
bool8 ZombieHorde_CanStep(struct ObjectEvent *zombie, u8 dir);
bool8 ZombieHorde_IsAggro(struct ObjectEvent *zombie);
bool8 IsZombieObjectEvent(const struct ObjectEvent *objectEvent);
const struct ZombieArea *ZombieHorde_GetCurrentArea(void);
void ZombieHorde_OnContact(struct ObjectEvent *zombie); // player <-> zombie contact / interaction
void ZombieHorde_RemoveAll(void);

#endif // GUARD_ZOMBIE_HORDE_H

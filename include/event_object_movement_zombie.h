// Included at the END of event_object_movement.c (needs its static helpers).
// Movement type: MOVEMENT_TYPE_ZOMBIE. All decisions live in zombie_horde.c.

#include "zombie_horde.h"

static const s16 sZombieIdleDelays[] = {16, 32, 48};

// 0: init
static bool8 MovementType_Zombie_Step0(struct ObjectEvent *objectEvent, struct Sprite *sprite)
{
    ClearObjectEventMovement(objectEvent, sprite);
    sprite->sTypeFuncId = 1;
    return TRUE;
}

// 1: think + pick a step
static bool8 MovementType_Zombie_Step1(struct ObjectEvent *objectEvent, struct Sprite *sprite)
{
    u8 dirs[5];
    u32 i;
    u8 mode = ZombieHorde_Think(objectEvent, dirs);

    if (mode == ZOMBIE_THINK_ALERT)
    {
        SetObjectEventDirection(objectEvent, dirs[0]);
        ObjectEventSetSingleMovement(objectEvent, sprite, MOVEMENT_ACTION_EMOTE_EXCLAMATION_MARK);
        PlaySE(SE_PIN);
        sprite->sTypeFuncId = 2;
        return TRUE;
    }
    // wandering zombies idle now and then
    if (mode == ZOMBIE_THINK_WANDER && Random() % 3 == 0)
    {
        SetMovementDelay(sprite, sZombieIdleDelays[Random() % ARRAY_COUNT(sZombieIdleDelays)]);
        sprite->sTypeFuncId = 4;
        return TRUE;
    }
    for (i = 0; dirs[i] != DIR_NONE; i++)
        if (ZombieHorde_CanStep(objectEvent, dirs[i]) && !GetCollisionInDirection(objectEvent, dirs[i]))
            break;
    if (dirs[i] == DIR_NONE) // boxed in
    {
        SetMovementDelay(sprite, 8);
        sprite->sTypeFuncId = 4;
        return TRUE;
    }
    SetObjectEventDirection(objectEvent, dirs[i]);
    if (ZOMBIE_CHASE_FAST && mode == ZOMBIE_THINK_CHASE)
        ObjectEventSetSingleMovement(objectEvent, sprite, GetWalkNormalMovementAction(objectEvent->movementDirection));
    else
        ObjectEventSetSingleMovement(objectEvent, sprite, GetWalkSlowMovementAction(objectEvent->movementDirection));
    objectEvent->singleMovementActive = TRUE;
    sprite->sTypeFuncId = 3;
    return TRUE;
}

// 2: wait for "!" to finish
static bool8 MovementType_Zombie_Step2(struct ObjectEvent *objectEvent, struct Sprite *sprite)
{
    if (ObjectEventExecSingleMovementAction(objectEvent, sprite))
    {
        sprite->sTypeFuncId = 1;
        return TRUE;
    }
    return FALSE;
}

// 3: wait for the step to finish
static bool8 MovementType_Zombie_Step3(struct ObjectEvent *objectEvent, struct Sprite *sprite)
{
    if (ObjectEventExecSingleMovementAction(objectEvent, sprite))
    {
        objectEvent->singleMovementActive = FALSE;
        if (ZombieHorde_IsAggro(objectEvent))
        {
            sprite->sTypeFuncId = 1;
        }
        else
        {
            SetMovementDelay(sprite, sZombieIdleDelays[Random() % ARRAY_COUNT(sZombieIdleDelays)]);
            sprite->sTypeFuncId = 4;
        }
    }
    return FALSE;
}

// 4: delay
static bool8 MovementType_Zombie_Step4(struct ObjectEvent *objectEvent, struct Sprite *sprite)
{
    if (WaitForMovementDelay(sprite))
    {
        ClearObjectEventMovement(objectEvent, sprite);
        sprite->sTypeFuncId = 1;
        return TRUE;
    }
    return FALSE;
}

static bool8 (*const sMovementTypeFuncs_Zombie[])(struct ObjectEvent *, struct Sprite *) =
{
    MovementType_Zombie_Step0,
    MovementType_Zombie_Step1,
    MovementType_Zombie_Step2,
    MovementType_Zombie_Step3,
    MovementType_Zombie_Step4,
};

movement_type_def(MovementType_Zombie, sMovementTypeFuncs_Zombie)

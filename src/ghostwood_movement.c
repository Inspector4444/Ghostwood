#include "global.h"
#include "ghostwood_movement.h"
#include "field_player_avatar.h"

// Last d-pad direction pressed, only valid while that button is still held.
static EWRAM_DATA u8 sLastPressedDir = DIR_NONE;
// A press waiting for the next tile boundary, and how many frames it stays valid.
static EWRAM_DATA u8 sBufferedDir = DIR_NONE;
static EWRAM_DATA u8 sBufferFrames = 0;
// Result of the latest GW_Movement_UpdateInput.
static EWRAM_DATA u8 sDpadDirection = DIR_NONE;

// Same fixed priority the vanilla field input uses when several keys are down.
static u32 DpadKeysToDirection(u16 keys)
{
    if (keys & DPAD_UP)
        return DIR_NORTH;
    if (keys & DPAD_DOWN)
        return DIR_SOUTH;
    if (keys & DPAD_LEFT)
        return DIR_WEST;
    if (keys & DPAD_RIGHT)
        return DIR_EAST;
    return DIR_NONE;
}

static u16 DirectionToDpadKey(u32 direction)
{
    switch (direction)
    {
    case DIR_NORTH:
        return DPAD_UP;
    case DIR_SOUTH:
        return DPAD_DOWN;
    case DIR_WEST:
        return DPAD_LEFT;
    case DIR_EAST:
        return DPAD_RIGHT;
    default:
        return 0;
    }
}

// The standard bike sets both bike flags, so only "acro without mach" is the Acro bike.
static bool32 IsAcroBike(void)
{
    return (gPlayerAvatar.flags & PLAYER_AVATAR_FLAG_ACRO_BIKE)
        && !(gPlayerAvatar.flags & PLAYER_AVATAR_FLAG_MACH_BIKE);
}

void GW_Movement_UpdateInput(u16 newKeys, u16 heldKeys)
{
    u32 pressed = DpadKeysToDirection(newKeys);
    u32 direction;

    if (pressed != DIR_NONE)
    {
        sLastPressedDir = pressed;
        sBufferedDir = pressed;
        sBufferFrames = GW_OW_INPUT_BUFFER_FRAMES;
    }
    else if (sBufferFrames != 0)
    {
        sBufferFrames--;
    }

    if (!(heldKeys & DirectionToDpadKey(sLastPressedDir)))
        sLastPressedDir = DIR_NONE;

    // The Acro bike's trick history relies on exact held keys.
    if (IsAcroBike())
    {
        sBufferFrames = 0;
        sDpadDirection = DpadKeysToDirection(heldKeys);
        return;
    }

    direction = DIR_NONE;
    if (GW_OW_LAST_PRESSED_WINS)
        direction = sLastPressedDir;
    // A tap that was already released still beats an older held direction,
    // so a quick tap while walking turns the corner at the next tile.
    if (direction == DIR_NONE && sBufferFrames != 0)
        direction = sBufferedDir;
    if (direction == DIR_NONE)
        direction = DpadKeysToDirection(heldKeys);

    sDpadDirection = direction;
}

u32 GW_Movement_GetDpadDirection(void)
{
    return sDpadDirection;
}

bool32 GW_Movement_IsTurnHeld(u16 heldKeys)
{
    return (heldKeys & GW_OW_TURN_BUTTON) != 0;
}

u32 GW_Movement_GetWalkState(u32 direction, u16 heldKeys)
{
    if (direction == DIR_NONE)
        return NOT_MOVING;

    // Turn button held: d-pad only turns, it never steps.
    if (GW_Movement_IsTurnHeld(heldKeys))
    {
        if (direction != GetPlayerMovementDirection())
            return TURN_DIRECTION;
        return NOT_MOVING;
    }

    return MOVING;
}

void GW_Movement_OnInputConsumed(void)
{
    sBufferFrames = 0;
    sBufferedDir = DIR_NONE;
}

void GW_Movement_ClearBuffer(void)
{
    GW_Movement_OnInputConsumed();
}

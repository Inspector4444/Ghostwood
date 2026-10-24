#ifndef GUARD_GHOSTWOOD_MOVEMENT_H
#define GUARD_GHOSTWOOD_MOVEMENT_H

// Ghostwood overworld movement feel.
//
// Covers walking / surfing and the Mach and standard bikes (CB1_Overworld).
// The Acro bike keeps raw held-key input because its trick detection compares
// against the raw key history, and cable club link movement is untouched.
//
// Each toggle can be overridden from a config header or the Makefile
// (e.g. -DGW_OW_INPUT_BUFFER_FRAMES=0) because they are #ifndef-guarded.

// 1: pressing a direction you are not facing moves you in that direction
//    straight away instead of spending a turn-in-place first.
//    0: vanilla tap-to-turn.
#ifndef GW_OW_NO_TAP_TURN
#define GW_OW_NO_TAP_TURN           1
#endif

// While this button is held, d-pad presses only turn the player (no steps).
// Spin-evolution still works, since it is fed by the turn-in-place path.
#ifndef GW_OW_TURN_BUTTON
#define GW_OW_TURN_BUTTON           L_BUTTON
#endif

// A d-pad press made while the player is still mid-step is remembered for
// this many frames and used at the next tile boundary. 0 disables buffering.
#ifndef GW_OW_INPUT_BUFFER_FRAMES
#define GW_OW_INPUT_BUFFER_FRAMES   6
#endif

// 1: if several directions are held, the most recently pressed one wins
//    (vanilla is a fixed Up > Down > Left > Right priority).
#ifndef GW_OW_LAST_PRESSED_WINS
#define GW_OW_LAST_PRESSED_WINS     1
#endif

// Acro bike: frames spent in the "turning" state before the bike actually
// turns (vanilla 6). The hop tricks (direction + B pressed within 4 frames of
// each other) are only detected during this window, so frame 0-3 must stay
// open: 4 trims two dead frames and keeps every trick; going lower breaks them.
#ifndef GW_OW_ACRO_TURN_WINDOW
#define GW_OW_ACRO_TURN_WINDOW      4
#endif

// Call once per frame from DoCB1_Overworld, before FieldGetPlayerInput.
void GW_Movement_UpdateInput(u16 newKeys, u16 heldKeys);

// The direction the player should act on this frame (DIR_NONE if none).
// Replaces the Up/Down/Left/Right priority chain in FieldGetPlayerInput.
u32 GW_Movement_GetDpadDirection(void);

// Replaces the NOT_MOVING / TURN_DIRECTION / MOVING decision for walking.
u32 GW_Movement_GetWalkState(u32 direction, u16 heldKeys);

// TRUE while the turn button is held (d-pad should only turn, never step).
bool32 GW_Movement_IsTurnHeld(u16 heldKeys);

// PlayerStep processed input this frame: any buffered press is spent.
void GW_Movement_OnInputConsumed(void);

// Drop buffered input (field controls locked, warps, scripts...).
void GW_Movement_ClearBuffer(void);

#endif // GUARD_GHOSTWOOD_MOVEMENT_H

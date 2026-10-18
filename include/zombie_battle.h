#ifndef GUARD_ZOMBIE_BATTLE_H
#define GUARD_ZOMBIE_BATTLE_H

// Zombie battle flow:
//   contact -> Register (+ script) -> ScriptStart (battle task/transition)
//   [2nd zombie touches during transition -> AddSecondZombie]
//   transition done -> OnTransitionDone (final flags + parties) -> battle
//   battle end -> script resumes -> Cleanup (remove zombies, roll drop)

bool8 ZombieBattle_IsPending(void);                       // anything registered/running
bool8 ZombieBattle_IsRegistered(struct ObjectEvent *z);
void ZombieBattle_Register(struct ObjectEvent *z);
void ZombieBattle_AddSecondZombie(struct ObjectEvent *z);
void ZombieBattle_Reset(void);

// callnative targets (data/scripts/zombie.inc)
void ZombieBattle_ScriptStart(void);
void ZombieBattle_Cleanup(void);                          // gSpecialVar_Result = TRUE if a drop was rolled

// hook for Task_BattleStart (battle_setup.c)
void ZombieBattle_OnTransitionDone(void);

// implemented in battle_setup_zombie.h (included by battle_setup.c)
void BattleSetup_StartZombieBattle(void);
void BattleSetup_FinalizeZombieBattle(bool8 twoOpponents, u16 trainerA, u16 trainerB);

void ZombieBattle_BeginFade(void);
bool8 IsZombieBattle(void);
bool8 ZombieBattle_RollFlee(void);
void ZombieBattle_NextDrop(void);

#endif // GUARD_ZOMBIE_BATTLE_H

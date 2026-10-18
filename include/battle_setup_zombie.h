// Included from battle_setup.c (after DoTrainerBattle) so it can use the file's
// static helpers. Keeps the zombie glue out of the main file.
void BattleSetup_StartZombieBattle(void);
void BattleSetup_FinalizeZombieBattle(bool8 twoOpponents, u16 trainerA, u16 trainerB);
static void CB2_EndZombieBattle(void);

void BattleSetup_StartZombieBattle(void)
{
    // Provisional flags; final ones are set when the transition ends,
    // once we know whether a second zombie joined.
    gBattleTypeFlags = BATTLE_TYPE_TRAINER;
    TRAINER_BATTLE_PARAM.opponentA = TRAINER_ZOMBIE_A;
    TRAINER_BATTLE_PARAM.opponentB = 0;
    gMain.savedCallback = CB2_EndZombieBattle;
    CreateBattleStartTask(GetWildBattleTransition(), 0);
    IncrementGameStat(GAME_STAT_TOTAL_BATTLES);
    IncrementGameStat(GAME_STAT_TRAINER_BATTLES);
    ScriptContext_Stop();
}

void BattleSetup_FinalizeZombieBattle(bool8 twoOpponents, u16 trainerA, u16 trainerB)
{
    u32 flags = BATTLE_TYPE_TRAINER;

    TRAINER_BATTLE_PARAM.opponentA = trainerA;
    TRAINER_BATTLE_PARAM.opponentB = twoOpponents ? trainerB : 0;
    if (twoOpponents)
        flags |= BATTLE_TYPE_DOUBLE | BATTLE_TYPE_TWO_OPPONENTS;
    if (FollowerNPCIsBattlePartner())
    {
        flags |= BATTLE_TYPE_MULTI | BATTLE_TYPE_INGAME_PARTNER | BATTLE_TYPE_DOUBLE;
        if (!twoOpponents)
            TRAINER_BATTLE_PARAM.opponentB = 0xFFFF;
    }
    gBattleTypeFlags = flags;
}

static void CB2_EndZombieBattle(void)
{
    CpuFill16(0, (void *)BG_PLTT, BG_PLTT_SIZE);
    ResetOamRange(0, 128);

    if (FollowerNPCIsBattlePartner())
    {
        RestorePartyAfterFollowerNPCBattle();
        if (FNPC_FLAG_HEAL_AFTER_FOLLOWER_BATTLE != 0
         && (FNPC_FLAG_HEAL_AFTER_FOLLOWER_BATTLE == FNPC_ALWAYS
         || FlagGet(FNPC_FLAG_HEAL_AFTER_FOLLOWER_BATTLE)))
            HealPlayerParty();
    }

    if (IsPlayerDefeated(gBattleOutcome) == TRUE && !FlagGet(B_FLAG_NO_WHITEOUT))
    {
        ZombieBattle_Reset();
        SetMainCallback2(CB2_WhiteOut);
    }
    else
    {
        // DowngradeBadPoison(); //?
        SetMainCallback2(CB2_ReturnToFieldContinueScriptPlayMapMusic); // resumes zombie.inc after waitstate
    }
}

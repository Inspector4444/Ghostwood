SewerHome_MapScripts::
	.byte 0

SewerHome_EventScript_Sketchy_Guy::
	lock
	faceplayer
	msgbox Sewer_Home_Text_WeaponsDealer, MSGBOX_DEFAULT
	release
	end

Sewer_Home_Text_WeaponsDealer:
	.string "Whatcha lookin' at!?\n"
	.string "I sell weapons, tools, the like.\p"
	.string "I'm not interested in selling\n"
	.string "to you!$"
	
SewerHome_EventScript_Crestfallen::
	lock
	msgbox Sewer_Home_Text_Crestfallen, MSGBOX_DEFAULT
	faceplayer
	playse SE_PIN
	applymovement LOCALID_CRESTFALLEN, Common_Movement_ExclamationMark
	delay 80
	msgbox Sewer_Home_Text_Crestfallen2, MSGBOX_DEFAULT
	applymovement LOCALID_CRESTFALLEN, Common_Movement_FaceOriginalDirection 
	waitmovement 0
	release
	end

Sewer_Home_Text_Crestfallen:
	.string "Is this sewer water the closest\n"
	.string "we'll see to a beautiful lake\l"
	.string "again?$"

Sewer_Home_Text_Crestfallen2:
	.string "Oh, {PLAYER}. Professor Dawn\n"
	.string "was looking for you.$"

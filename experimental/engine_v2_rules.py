"""Experimental V2 shot-contact, free throw and rebound resolution.

Provisional probabilities, deliberately NOT NBA calibrated.
"""
from engine_v2 import clamp, chance, skill

def free_throws(rng, shooter, attempts, events, *, return_last=False):
    # Free throw rating not yet in Player; use touch proxy until data migration.
    touch=(skill(shooter,"mid_range")*.45+skill(shooter,"close_shot")*.30+
           skill(shooter,"three_point")*.25)
    p=clamp(.74+(touch-75)*.003, .40,.96)
    results=[chance(rng,p) for _ in range(attempts)]
    made=sum(results)
    events.append(f"rules: {shooter.name} free throws {made}/{attempts}")
    return (made, results[-1] if results else True) if return_last else made

def shooting_foul(rng, shooter, primary, helper, zone, events):
    defenders=[primary]+([helper] if helper is not None else [])
    # Higher defensive IQ reduces unnecessary contact; aggressive rim defense
    # increases the number of contact opportunities.
    contact=sum(.012+(100-skill(d,"defensive_iq"))*.00045 for d in defenders)
    if zone=="rim":
        contact*=2.2
    if chance(rng,clamp(contact,0,.32)):
        culprit=defenders[0] if len(defenders)==1 or chance(rng,.55) else defenders[1]
        events.append(f"rules: shooting foul by {culprit.name}")
        return culprit.name
    return None

def rebound(rng, offense, defense, events):
    """Return (offense_won, player_index). Rebound battle considers all ten players."""
    offensive=[max(1,skill(p,"offensive_rebound")*.70+
                   skill(p,"vertical")*.18+skill(p,"strength")*.12) for p in offense]
    defensive=[max(1,skill(p,"defensive_rebound")*.70+
                   skill(p,"vertical")*.18+skill(p,"strength")*.12) for p in defense]
    # Defense has positioning advantage on a normal shot.
    off_weight=sum(x**2 for x in offensive)*.65
    def_weight=sum(x**2 for x in defensive)
    is_off=chance(rng,off_weight/(off_weight+def_weight))
    weights=offensive if is_off else defensive
    index=rng.choices(range(5),weights=[x*x for x in weights],k=1)[0]
    events.append(f"rules: {'offensive' if is_off else 'defensive'} rebound by "
                  f"{(offense if is_off else defense)[index].name}")
    return is_off,index

def offensive_foul(rng, attacker, defender, action, events):
    """Charging and illegal screens; ball changes hands without free throws."""
    if action not in ("drive","screen","post"):
        return False
    base={"drive":.017,"screen":.024,"post":.014}[action]
    control=(skill(attacker,"ball_handle") if action=="drive" else
             skill(attacker,"strength") if action=="post" else skill(attacker,"shot_iq"))
    p=clamp(base+(skill(defender,"defensive_iq")-75)*.00035
            -(control-75)*.0002,0,.10)
    if chance(rng,p):
        events.append(f"rules: offensive foul ({action}) by {attacker.name}")
        return True
    return False

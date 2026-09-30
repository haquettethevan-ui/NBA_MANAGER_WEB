SALARY_CAP_2026_27 = 164_961_000
LUXURY_TAX_2026_27 = 200_428_000
FIRST_APRON_2026_27 = 209_015_000
SECOND_APRON_2026_27 = 221_686_000

def fallback_salary(overall):
    """Temporary salary valuation when no imported 2026-27 contract is available."""
    o=int(overall or 70)
    if o>=95:return 55_000_000
    if o>=90:return 42_000_000
    if o>=86:return 30_000_000
    if o>=82:return 20_000_000
    if o>=78:return 12_000_000
    if o>=74:return 6_000_000
    return 2_500_000

def salary_for_row(row):
    value=row.get("salary_2026_27")
    return int(value) if value not in (None,"") else fallback_salary(row.get("overall",70))

def payroll_zone(payroll):
    p=int(payroll)
    if p>SECOND_APRON_2026_27:return "second_apron"
    if p>FIRST_APRON_2026_27:return "first_apron"
    if p>LUXURY_TAX_2026_27:return "tax"
    if p>SALARY_CAP_2026_27:return "over_cap"
    return "under_cap"

def validate_trade_salary(payroll,outgoing,incoming,outgoing_players=1):
    payroll=int(payroll);outgoing=int(outgoing);incoming=int(incoming)
    if payroll>SECOND_APRON_2026_27 and int(outgoing_players)>1:
        raise ValueError("Trade refuse : une equipe au-dessus du Second Apron ne peut pas agreger plusieurs salaires.")
    limit=outgoing if payroll>FIRST_APRON_2026_27 else int(outgoing*1.25)+100_000
    if incoming>limit:
        if payroll>FIRST_APRON_2026_27:
            raise ValueError("Trade refuse : au-dessus du First Apron, le salaire recu ne peut pas depasser le salaire envoye.")
        raise ValueError(f"Trade refuse : salaire recu trop eleve (maximum {limit/1_000_000:.2f} M$).")
    return True

def validate_cap(before,after):
    return True

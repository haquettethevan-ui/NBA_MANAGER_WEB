SALARY_CAP_2026_27 = 164_961_000

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

def validate_cap(before,after):
    before=int(before);after=int(after)
    if before<=SALARY_CAP_2026_27:
        if after>SALARY_CAP_2026_27:
            raise ValueError(f"Trade refusé : la masse salariale dépasserait le salary cap ({SALARY_CAP_2026_27/1_000_000:.3f} M$).")
    elif after>before:
        raise ValueError("Trade refusé : une équipe déjà au-dessus du salary cap ne peut pas augmenter sa masse salariale.")
    return True

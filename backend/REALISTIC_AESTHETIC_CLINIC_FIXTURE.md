# Tia realistic aesthetic clinic fixture

This fixture turns the non-production `tia` workspace into a production-like multi-branch
laser/aesthetic clinic dataset for realistic agent testing.

It intentionally **refuses to run when `ENVIRONMENT=production`**. The catalog is synthetic,
so real clinic prices, addresses, doctor credentials and phone numbers must still come from the
actual clinic onboarding flow before a real deployment.

## What it seeds

- 3 active branches: Nasr City, New Cairo, Sheikh Zayed.
- 28 services across laser hair removal, skin lasers, facials, dermatology, injectables and hair treatment.
- 7 doctors with different service scopes.
- Single-branch doctors and multi-branch doctors.
- Different doctor schedules per branch.
- A split shift for Dr Ahmed (Tuesday 16:00-19:00 and 20:00-22:00) to test schedule gaps.
- Per-doctor custom service duration/price overrides.
- Branch working hours including a closed Friday in New Cairo.
- 15-minute slot intervals, 60-minute minimum notice and a 120-day booking horizon.
- Optional synthetic patients and appointment cases for conflict/lifecycle testing.

## Important legacy cleanup

By default the seed deactivates old clinic-core records whose branch code or service slug starts
with `demo-` or `regression-`, plus doctors clearly marked Demo/Regression. Historical rows are
not deleted, so existing foreign-key references remain valid.

Use `--keep-legacy-active` only when you explicitly want the old fixture records to remain active.

## Run it

From `backend`:

```powershell
python scripts\seed_realistic_aesthetic_clinic.py --workspace-slug tia
```

Preview without writing:

```powershell
python scripts\seed_realistic_aesthetic_clinic.py --workspace-slug tia --dry-run
```

Clinic core only, without synthetic patient/appointment cases:

```powershell
python scripts\seed_realistic_aesthetic_clinic.py --workspace-slug tia --without-scenarios
```

You can also target a workspace explicitly:

```powershell
python scripts\seed_realistic_aesthetic_clinic.py --workspace-id YOUR_WORKSPACE_UUID
```

## Realistic test cases

1. **Exact generic service resolution**
   - `عايز احجز ليزر إزالة الشعر مع دكتور احمد في مدينة نصر الثلاثاء بعد 6`
   - The generic exact service exists even though several area-specific laser services also exist.

2. **Doctor works in one branch only**
   - Dr Ahmed Mahmoud is assigned only to Nasr City.
   - Ask for him in New Cairo and verify that Tia does not invent an assignment.

3. **Doctor works in two branches on different days**
   - Dr Mariam Hassan works Nasr City on Monday/Wednesday and New Cairo on Tuesday/Sunday.

4. **Split shift / unavailable gap**
   - Dr Ahmed on Tuesday has 16:00-19:00 and 20:00-22:00.
   - Ask for 19:30 and verify that it is unavailable even though the branch is open.

5. **Existing confirmed appointment blocks a slot**
   - A confirmed Dr Ahmed appointment is seeded for the next Tuesday at 18:00.
   - Availability should not offer the overlapping slot.

6. **Cancelled appointment does not block availability**
   - A cancelled Dr Ahmed appointment is seeded for the next Thursday at 18:00.

7. **Pending appointment blocks availability**
   - Dr Sara has a seeded pending appointment on the next Wednesday at 14:00 in New Cairo.

8. **Custom doctor-service duration/price**
   - Dr Ahmed has a custom generic laser duration/price.
   - Dr Nour has a custom Botox duration/price.
   - Dr Youssef has a custom men's back/chest laser duration/price.
   - Dr Hala has a custom Hydrafacial duration/price.

9. **Service not offered by a selected doctor**
   - Ask Dr Ahmed for Botox, or Dr Nour for tattoo removal.
   - Tia should not fabricate availability.

10. **Medical-review service**
    - Fractional CO2, pigmentation laser, tattoo removal, injectables, PRP and similar services have
      `requires_medical_review=True` so medical-safety/handoff behavior can be exercised.

11. **Closed branch day**
    - New Cairo has no Friday branch-hours row.
    - Ask for New Cairo on Friday and verify no slots are offered.

12. **Multiple upcoming appointments**
    - The synthetic patient `كريم أكثر من موعد` has two upcoming appointments, useful for testing
      cancel/reschedule flows that must ask which appointment the patient means.

13. **Historical lifecycle**
    - Synthetic completed, cancelled and no-show appointments are included for history/status testing.

14. **Blocked patient**
    - A synthetic blocked patient is present to validate that booking writes are refused.

## Safety

The fixture uses reserved-looking `+200000...` synthetic phone numbers and does not create messages,
dispatches or outbound communication jobs. It only writes clinic core, synthetic patients and
appointments into the selected non-production workspace.

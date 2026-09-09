from pathlib import Path

path = Path("frontend/src/app/(dashboard)/patients/[patientId]/page.tsx")
text = path.read_text(encoding="utf-8")

old_import = 'import { addPatientNote, createPatientTask, setPatientWhatsappOptIn } from "../actions";\n'
new_import = old_import + 'import { PatientPackagePanel } from "./package-panel";\n'
if text.count(old_import) != 1:
    raise RuntimeError("patient package panel import marker mismatch")
text = text.replace(old_import, new_import, 1)

old_panel = '''          </Card>\n\n          <Card>\n            <CardHeader><CardTitle>ملاحظات العميل</CardTitle></CardHeader>\n'''
new_panel = '''          </Card>\n\n          <PatientPackagePanel patientId={patient.id} />\n\n          <Card>\n            <CardHeader><CardTitle>ملاحظات العميل</CardTitle></CardHeader>\n'''
if text.count(old_panel) != 1:
    raise RuntimeError("patient package panel placement marker mismatch")
text = text.replace(old_panel, new_panel, 1)
path.write_text(text, encoding="utf-8")

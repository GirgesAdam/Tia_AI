# Apply the professional README

Copy `README.md` from this patch to the repository root and replace the existing file.

Suggested Git workflow:

```powershell
git checkout -b docs/professional-readme
Copy-Item <downloaded-patch>\README.md .\README.md -Force
git add README.md
git commit -m "docs: present the complete Tia AI platform"
git push -u origin docs/professional-readme
```

Open a Pull Request into `main` and merge after CI passes.

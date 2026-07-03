# Region 1 Beta Test Workspace

This folder is the prepared beta workspace for running Municipal AI OS against real Region 1 Excel files.

## Folder layout

- `inbox/`: place real Region 1 `.xlsx` files here before each beta run.
- `runs/`: run-specific outputs are written here by the existing collection agent.
- `state/`: duplicate-run lock and seen-file state are written here.
- `audit/`: full audit logs are written here.

Do not commit real taxpayer Excel files or generated production outputs. The `.gitkeep` files only preserve the beta folder structure.

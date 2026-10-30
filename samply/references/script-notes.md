# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/samply_cli.py

- Step 1: request a signed upload URL. With parentid = a stack id, the upload lands as that stack's newest version. The empty version box exists from this moment on.
- Step 2: PUT the bytes to the signed URL with the x-goog-meta headers it was signed over.

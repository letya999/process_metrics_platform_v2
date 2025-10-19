# Git Workflow Guide

## Daily Branch Workflow

This guide describes the recommended Git workflow for daily development tasks.

### Morning: Start a New Feature Branch

```bash
# 1. Switch to main and ensure it's up to date
git switch main
git pull  # If working with a remote repository

# 2. Create a new feature branch (use descriptive names with date)
git switch -c feature/day-work-MMDD  # Example: feature/day-work-1019 or chore branch

# 3. Verify you're on the correct branch
git branch --show-current
```

### During the Day: Make and Commit Changes

```bash
# 4. Work on your code and make changes...

# 5. Stage and commit your changes
git add .  # Or specify files: git add file1.py file2.py
git commit -m "type: descriptive message"  # Example: "feat: implement user validation"

# 6. Continue working and committing as needed
git add .
git commit -m "fix: resolve edge case in validation"

# 7. Check your commit history
git log --oneline --graph --decorate -10
```

### End of Day: Merge to Main

```bash
# 8. Switch back to main
git switch main

# 9. Update main (if working with remote)
git pull

# 10. Merge your feature branch into main
git merge feature/day-work-MMDD

# 11. If conflicts occur, resolve them and then:
git add .
git commit -m "merge: resolve conflicts between main and feature branch"

# 12. Optional: Delete the feature branch if no longer needed
git branch -D feature/day-work-MMDD
```

## Useful Commands

### Branch Management

```bash
# List all branches
git branch -v

# Create and switch to a new branch
git switch -c branch-name

# Delete a branch
git branch -D branch-name
```

### Visualization

```bash
# View branch structure and history
git log --graph --oneline --all --decorate

# Show current branch
git branch --show-current
```

### Troubleshooting

```bash
# Check status of working directory
git status

# Discard changes in working directory
git restore file-name  # For specific file
git restore .          # For all files

# Unstage changes
git restore --staged file-name
```

## Commit and branch Types

- `feat`: New feature
- `fix`: Bug fix
- `chore`: Routine tasks, maintenance
- `test`: Adding or correcting tests
- `merge`: Merge conflict resolution

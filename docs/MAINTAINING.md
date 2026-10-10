# Maintainer guide

How the automation is wired, the one-time setup it needs, and the day-to-day routine.

## How it fits together

```
Issue form ──► submission.yml ──► contributor checks ──► content + link checks ──► PR (by the app)
                                      │ fail                    │ fail
                                      ▼                         ▼
                              comment + close           comment + needs-changes
                                                        (author edits the issue → re-check)

Direct PR ──► pr-guard.yml (API only, never runs PR code) ──► labels / comment / close
          └─► ci.yml (tests, validate changed entries, load their links)

Merge to main ──► publish-readme.yml ──► README.md regenerated and committed by the app
Every Monday  ──► maintenance.yml ──► "Link check report" and "Stale entries report" issues
```

| File | Purpose |
| --- | --- |
| `data/entries/*.yml` | One file per entry; the source of truth for the README tables |
| `data/categories.yml` | Section ids, numbers, and titles (must match the README headings and the form dropdown) |
| `.github/submission-policy.yml` | Thresholds, rate limits, blocklists |
| `scripts/submission.py` | Issue form → checks → pull request |
| `scripts/pr_guard.py` | Rules for pull requests opened directly |
| `scripts/validate.py` | Schema and policy validation (CI) |
| `scripts/build_readme.py` | Renders the generated regions of `README.md` |
| `scripts/maintenance.py` | Weekly link and staleness reports; README publishing |

## One-time setup

### 1. Create the GitHub App

1. **Settings → Developer settings → GitHub Apps → New GitHub App** (on the `lentrade` account).
2. Name: for example `trading-awesome-bot`. Homepage URL: the repository URL.
3. **Webhook:** uncheck **Active**.
4. **Repository permissions:**
   - Contents: **Read and write**
   - Issues: **Read and write**
   - Pull requests: **Read and write**
   - Metadata: Read-only (mandatory)
5. **Where can this GitHub App be installed?** Only on this account.
6. Create the app, then **Generate a private key** (a `.pem` file downloads) and note the **Client ID**.
7. **Install App** → only select repository → `lentrade/trading-awesome`.

### 2. Store the credentials in an environment

1. Repository **Settings → Environments → New environment** named `submission-bot`.
2. **Deployment branches and tags:** Selected branches → `main` only.
3. Add environment **secret** `BOT_PRIVATE_KEY` with the full contents of the `.pem` file.
4. Add environment **variable** `BOT_CLIENT_ID` with the app's Client ID.
5. Delete the downloaded `.pem` file from your computer once it is stored.

The workflows that need the app (`submission.yml`, `publish-readme.yml`) run in this environment. Each run appears as a deployment in the repository sidebar; that is expected.

### 3. Protect `main` with a ruleset

**Settings → Rules → Rulesets → New branch ruleset**, target the default branch:

- Restrict deletions; block force pushes
- Require a pull request before merging: 1 approval, dismiss stale approvals, **require review from Code Owners**
- Require status checks to pass: `Validate data` (from CI) only. Do **not** require `actionlint` or `zizmor`: they run only when workflow files change, so pull requests that do not touch workflows would wait for them forever.
- **Bypass list:** the GitHub App with mode **Always** (so `publish-readme.yml` can commit the regenerated README), and the **Repository admin** role with mode **For pull requests only** (so a solo maintainer can merge their own pull requests without pushing directly)

### 4. Repository settings

- **Settings → Actions → General**
  - Fork pull request workflows from outside collaborators: **Require approval for all external contributors**
  - Workflow permissions: **Read repository contents and packages permissions**
  - **Uncheck** "Allow GitHub Actions to create and approve pull requests" (the app opens pull requests; `GITHUB_TOKEN` does not need to)
- **Settings → General → Pull Requests:** enable **Automatically delete head branches** (cleans up `submission/issue-N` branches after merge)
- **Settings → Advanced Security** (or Code security): enable **Private vulnerability reporting**, **Dependabot alerts**, **Secret scanning**, and **Push protection**
- **About** (repository home page, gear icon): add topics `awesome`, `awesome-list`, `algorithmic-trading`, `quantitative-finance`, `market-data`, `backtesting`, `crypto`, `trading`; remove unrelated topics
- Optional: **Settings → General → Features → Discussions** for general questions

### 5. Labels

**Create `submission`, `new-entry`, `update-entry`, `broken-link`, `feedback`, and `maintainer-approved` before anyone uses the forms.** GitHub silently drops issue-form labels that do not exist in the repository, and the submission bot only reacts to issues labelled `submission`. The other labels are created automatically (in grey) the first time the automation applies them.

| Label | Meaning |
| --- | --- |
| `submission`, `new-entry`, `update-entry` | Set by the issue forms |
| `needs-changes` | The bot found problems the author must fix |
| `trust-check-failed` | Contributor rules failed; the issue or PR was closed |
| `maintainer-approved` | Apply to re-run a submission without contributor rules |
| `pr-opened` | The bot opened a pull request for this submission |
| `vendor-submitted` | The contributor declared an affiliation |
| `needs-manual-review` | Soft signals or something the bot could not verify |
| `domain-change` | An entry's website moves to a different domain; verify ownership |
| `use-submission-form` | A first-time contributor opened a PR that adds an entry |
| `sensitive-change` | A PR touches automation or policy files |
| `link-report`, `stale-report` | Weekly tracking issues |
| `broken-link`, `feedback` | Set by the corresponding issue forms |

## Day-to-day

**Reviewing a bot pull request.** Read the preview row and the "Needs a human look" section. Check that the description is neutral, the category fits, and the pricing source matches. For `vendor-submitted` entries, be stricter about wording. Edit the YAML directly in the PR if small fixes are needed, then merge. The README updates itself.

**Overriding the contributor rules.** If a legitimate contributor fails the account-age check, review the request yourself and add the `maintainer-approved` label to the issue. The bot reopens it and re-runs the content checks. Only labels applied by users with write access count.

**Domain changes.** Never merge a `domain-change` without evidence: the old domain redirecting to the new one, or an announcement on a channel the organization already controlled.

**Weekly reports.** Work through the "Link check report" issue: replace moved links, mark dead services deprecated (`status: deprecated` with a `deprecation_note`), and treat unexpected cross-domain redirects as potential hijacks; remove the link first, then investigate. The "Stale entries report" lists entries whose `last_verified` date is old.

**Blocking abuse.** Add logins or domains to `.github/submission-policy.yml` (`blocked_users`, `blocked_domains`).

**Running checks locally.**

```bash
python -m pip install --require-hashes -r scripts/requirements.txt
python -m unittest discover -s tests
python scripts/validate.py
python scripts/maintenance.py links --no-github      # full link check, prints a report
python scripts/submission.py --event event.json --offline   # replay a saved issues event
```

## Updating pinned actions

Every action is pinned to a full commit SHA with the version in a comment. Dependabot opens grouped update pull requests weekly (with a 7-day cooldown for new releases); the `Workflow lint` checks run `actionlint` and `zizmor` on them.

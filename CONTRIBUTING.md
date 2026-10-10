# Contributing to Trading Awesome

Thanks for helping keep this list accurate and useful. This guide covers who can contribute, what belongs on the list, how vendors may take part, and how the automated checks and the human review work.

## Quick start

| I want to… | Do this |
| --- | --- |
| Add a service | Fill in the [**Add a service**](https://github.com/lentrade/trading-awesome/issues/new?template=new-entry.yml) form. A bot checks it and opens a pull request for you. |
| Fix pricing, a description, or a URL | Use the [**Update an entry**](https://github.com/lentrade/trading-awesome/issues/new?template=update-entry.yml) form, or open a pull request that edits `data/entries/<name>.yml`. |
| Report a dead link | Use the [**Report a broken link**](https://github.com/lentrade/trading-awesome/issues/new?template=broken-link.yml) form. |
| Report a scam, phishing, or hijacked link | Report it **privately**, see [SECURITY.md](SECURITY.md). |
| Improve the guides (Quick Start, FAQ, Comparisons) | Open a pull request, or suggest it with the [**Suggest an improvement**](https://github.com/lentrade/trading-awesome/issues/new?template=feedback.yml) form. |

> **Do not edit the tables in `README.md` by hand.** They are generated from [`data/entries/`](data/entries/) and rebuilt automatically after every merge. CI rejects hand edits to the generated tables.

## Who can submit

The list is a frequent target for spam and for scam projects that want a credible-looking backlink, so the automation applies these rules before a maintainer looks at anything:

| Rule | New entries | Updates |
| --- | --- | --- |
| Minimum GitHub account age | **90 days** | **30 days** |
| Account type | Personal account (no bots or organizations) | Same |
| Open submissions per person | 1 at a time | Same |
| Submissions per person | 3 per 30 days | Same |

- Contributors with a **previously merged pull request** here skip the account-age rule.
- New entries from first-time contributors must go through the **Add a service** form. Pull requests that add a new entry directly are closed with a pointer to the form, which runs the same checks and opens the pull request for you.
- Some signals do not block a submission but flag it for a closer look, for example a young account without public repositories.
- If the checks reject you by mistake, reply on the issue. A maintainer can review it manually and apply the `maintainer-approved` label to re-run the checks without the contributor rules.

The exact thresholds are in [`.github/submission-policy.yml`](.github/submission-policy.yml).

## What we list

A service should meet at least **two** of these criteria:

1. A **public API** with documented endpoints
2. An **active open-source repository** (commits in the last 6 months, responsive maintainers)
3. **Significant developer adoption** (GitHub stars, community packages, forum activity)
4. A **distinctive specialization** that fills a gap in the existing entries
5. **Broad market coverage** or **deep data quality**

Open-source libraries should also have at least one commit in the last 12 months, respond to issues, and have no known critical vulnerabilities left unaddressed. Archived repositories are not accepted.

## What we decline

- Affiliate links, referral codes, invite links, and tracking parameters
- Services with neither a public API nor an open-source offering, unless they are widely used research tools (see section 5)
- Abandoned projects (no commits in 12+ months, no response to issues)
- Duplicates of an existing entry, and separate entries for every product of one vendor
- Websites on domains registered less than **90 days** ago
- Tokens, coins, presales, airdrops, and "earn" or yield products
- Trading signals sold as investment advice, copy-trading schemes, and anything promising returns ("guaranteed", "risk-free", "100x")
- Services that require a deposit before you can see the product or documentation

## Vendor and affiliation policy

Vendors may submit and maintain their own entries. These rules keep that fair for readers and for competing services:

- **Disclose the relationship.** The forms ask about it, and it is shown on the pull request. Employees, founders, contractors, agencies, and anyone paid or asked by the vendor count as affiliated.
- **One entry per product.** List additional products only when they serve a clearly different purpose and belong in a different section.
- **Neutral wording.** Descriptions state what the product does, not why it is great. Maintainers may edit wording before merging.
- **No paid placement.** We do not accept payment, sponsorship, tokens, or favors for listings, placement, or reviews. Offers of payment lead to rejection.
- **Undisclosed affiliation** discovered later leads to removal of the related entries and may block the account.
- After a rejection, wait **90 days** before submitting the same service again unless a maintainer invites you to.

## Link and domain changes

Changing the website of an existing entry is the most common way scams get into curated lists: a legitimate entry is accepted, and later its link is "updated" to a look-alike or a hijacked domain.

- Changes within the same domain (a new path, `www.`, a docs subdomain) are routine.
- **Moving an entry to a different domain** needs evidence that the new domain belongs to the same organization: the old site redirects there, or an official announcement on a channel the organization already controlled (old website, verified social account, GitHub organization) confirms it. Link the evidence in the **Source URL** field or in the pull request.
- The automation labels such changes `domain-change`, and a maintainer verifies them before merging.
- A weekly job also reports listed sites that start redirecting to a different domain on their own.

## Entry format

Each entry is one YAML file in [`data/entries/`](data/entries/), named after the service (`kebab-case`, for example `twelve-data.yml`). The submission bot writes these files for you; for direct pull requests, follow this format:

```yaml
name: Acme Data
url: https://acme.example/
category: market-data
description: REST and WebSocket API for U.S. equities and options data with official Python and Go clients.
scope: U.S. equities / options; Traditional markets; Research / automation
api: '[API docs](https://docs.acme.example/) · Py: [official](https://github.com/acme/acme-python) · Go: [community](https://github.com/someone/acme-go) · PHP: —'
pricing: Free tier; paid plans start at **$29/month**; see [official pricing](https://acme.example/pricing).
repo: https://github.com/acme/acme-python
affiliation: vendor
added: 2026-10-10
last_verified: 2026-10-10
```

| Field | Required | Rules |
| --- | --- | --- |
| `name` | yes | The brand's own capitalization. Must be unique. |
| `url` | yes | Official site over HTTPS, no tracking or referral parameters. |
| `category` | yes | A section `id` from [`data/categories.yml`](data/categories.yml). |
| `description` | yes | One factual sentence ending with a period; new descriptions stay under 250 characters. |
| `scope` | yes | Short coverage detail, then one or more coverage labels (below), separated by `; `. |
| `api` | yes | `[API docs](…)` (or `No public API identified`), then `Py`, `Go`, `PHP` package links marked `official` or `community`, or `—`. Link source repositories, not registry pages. |
| `pricing` | yes | Public entry price or plan description with a link to the source. Use "contact sales" only when no public price exists. |
| `repo` | no | Main GitHub repository, used by the weekly maintenance report. |
| `status` | no | `active` (default) or `deprecated`, with `deprecation_note`. |
| `affiliation` | no | `none`, `vendor`, or `other`. Set by the submission form. |
| `added` | yes | Date the entry joined the list (`YYYY-MM-DD`). |
| `last_verified` | yes | Date someone last checked the entry against the provider's site. Update it whenever you verify pricing or details. |

Text fields must fit on one line and must not contain `|`, HTML, images, bare URLs, or hidden Unicode characters.

### Coverage labels

- `Crypto — spot / on-chain / DeFi`
- `Crypto — derivatives`
- `Traditional markets`
- `Forex / FX`
- `Brokerage / execution`
- `Research / automation`

## Style guide

- Write in **English** with U.S. spelling. Use "U.S.", not "US".
- Be factual. Avoid superlatives and marketing language ("best", "leading", "fastest", "revolutionary").
- Use `**bold**` for prices and `code` for package names and technical terms.
- Always give links descriptive text; never paste bare URLs.
- When you verify a price, update `last_verified`. Optionally note "(verified YYYY-MM-DD)" in the pricing text.

## How review works

1. **Automated checks.** The submission bot or the PR guard checks the contributor rules. CI validates every entry file (required fields, link policy, wording, duplicates), loads the links of changed entries, and runs the unit tests.
2. **Human review.** A maintainer checks accuracy, relevance, neutrality, and the affiliation disclosure. Nothing is merged automatically.
3. **Publish.** After merge, a workflow regenerates `README.md` from the data files.

Typical review time is **3–7 days**.

## Removal and deprecation

An entry is removed or marked deprecated when:

- Its links stay broken for **30 days** of weekly checks
- The service shuts down, is acquired and discontinued, or closes its API
- Its repository is archived or has no activity for more than 12 months without a maintained successor
- It no longer meets the editorial criteria, or the affiliation policy was violated

A **compromised or malicious** link is removed immediately; see [SECURITY.md](SECURITY.md). Vendors can request removal of their own entry with the update form.

## Working locally

```bash
python -m pip install --require-hashes -r scripts/requirements.txt
python scripts/validate.py              # check every entry
python scripts/validate.py --base main  # also apply the rules for changed entries
python scripts/build_readme.py          # optional: preview README.md
python -m unittest discover -s tests    # run the tests
```

## License

By contributing, you dedicate your contribution to the public domain under [CC0 1.0](LICENSE), like the rest of this list.

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). In short: be respectful, disclose affiliations, and focus on the quality of information, not on competitive positioning.

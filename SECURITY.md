# Security Policy

This repository is a directory of links to trading and market-data services. Many of them handle money, API keys, or crypto wallets, so a single malicious link can cause real losses. We treat reports about compromised or deceptive links with the same urgency as vulnerabilities in code.

## What to report

**Malicious or compromised listings**

- A listed link that now leads to phishing, a wallet drainer, malware, or a fake login page
- A domain that expired, was sold, or was taken over by someone other than the original service
- Typosquatted or look-alike URLs (for example `binnance.com` or Unicode look-alikes)
- An official SDK or package link that points to a compromised, hijacked, or impersonating repository
- An entry that impersonates a real service, or a service that is presented as something it is not

**This repository's automation**

- Vulnerabilities in the GitHub Actions workflows or the scripts in [`scripts/`](scripts/), such as command or script injection from issue or pull-request content, token exposure, or ways to bypass the contributor and link checks
- Ways to get content merged or published without maintainer review

**Out of scope**

- Vulnerabilities in the listed services themselves. Report those to the vendor; we will update or remove the entry if a vendor is unresponsive and users are at risk.
- Disagreements about whether a service belongs on the list. Open a regular issue instead.
- Spam submissions. The automation closes those; you can still flag them in a regular issue.

## How to report

Please report privately through **[GitHub private vulnerability reporting](https://github.com/lentrade/trading-awesome/security/advisories/new)** (Security tab → "Report a vulnerability"). Do not open a public issue for an active scam or an automation vulnerability, because that alerts the attacker before the link is removed.

Include as much as you can:

- The entry name and the exact URL
- What you observed (screenshots, redirect chain, `curl -I` output, WHOIS or certificate details)
- When you first noticed it
- For automation issues: the workflow or script, the input that triggers the problem, and the impact

## What happens next

| Step | Target |
| --- | --- |
| Acknowledge the report | within 72 hours |
| Malicious or compromised link confirmed | link removed or the entry disabled within 24 hours of confirmation |
| Automation vulnerability confirmed | fix or mitigation within 14 days |
| Public disclosure | after the fix, coordinated with the reporter, with credit if you want it |

If a link is clearly dangerous, a maintainer removes it first and investigates afterwards. A removed entry can be restored once the vendor shows that the domain or repository is back under its control.

## How the list protects itself

- **Contributor checks.** New entries must come from GitHub accounts at least 90 days old (30 days for updates) unless the contributor already has a merged contribution. Submissions are rate-limited per account, and a blocklist covers known abusers. Thresholds live in [`.github/submission-policy.yml`](.github/submission-policy.yml).
- **Link policy.** Only HTTPS. No URL shorteners, referral or affiliate codes, tracking parameters, IP addresses, punycode hostnames, or hidden Unicode characters. Submitted sites must not redirect to another domain, and new domains must be at least 90 days old.
- **Domain-change review.** Changing an entry's website to a different domain needs proof that the new domain belongs to the same organization; the automation labels such changes `domain-change` for manual review.
- **Weekly monitoring.** A scheduled job re-checks every link and reports listed sites that start redirecting to a different domain, which is a common sign of an expired or hijacked domain.
- **No automatic merges.** Every pull request, including the ones the submission bot opens, is reviewed and merged by a maintainer.
- **Hardened automation.** Workflows run with least-privilege tokens, pin every action to a commit SHA, never execute code from pull requests, and parse issue content as data only. Dependabot keeps pins current, and `zizmor` and `actionlint` check every workflow change.

## Stay safe when using listed services

- Inclusion is **not an audit or an endorsement**. Verify every service yourself before you connect accounts or move funds.
- Type or bookmark official URLs. Check the domain before you sign in or connect a wallet.
- The maintainers will **never** contact you by direct message, ask for API keys, passwords, or seed phrases, or announce tokens, airdrops, or giveaways. Anyone who does is impersonating us.
- Create API keys with the least privileges you need. Disable withdrawal permissions for automated systems and restrict keys by IP where possible. See the [FAQ](FAQ.md#security) for more.

## Supported versions

Only the `main` branch is maintained.

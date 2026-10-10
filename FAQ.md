# Frequently Asked Questions

## General

### Why this list exists

**Q: There are dozens of "awesome-trading" lists already. Why another one?**

A: Most existing lists are either (1) abandoned since 2020–2022, (2) focused on a single language or asset class, or (3) mix data APIs with brokerage APIs as if they solve the same problem. This list is cross-asset, explicitly separates *data* from *execution*, and is checked by automation every week.

**Q: How often is this list updated?**

A: Continuously. New entries and corrections arrive through the submission forms and pull requests. Every Monday a scheduled job checks all links and flags sites that started redirecting to another domain, and a second report lists entries whose pricing has not been verified for six months. Each entry records its `added` and `last_verified` dates in [`data/entries/`](data/entries/).

**Q: Is a listing an endorsement?**

A: No. Entries are sorted alphabetically, not ranked. Inclusion reflects editorial criteria such as breadth, reliability, API maturity, and developer ecosystem (see [CONTRIBUTING.md](CONTRIBUTING.md#what-we-list)). It is **not** investment advice, a performance claim, market-share data, or a security audit of the service.

**Q: Do you accept payment for listings?**

A: No. We never accept payment, sponsorship, tokens, or favors for listings or placement. Vendors may submit their own products, but they must disclose the relationship, and every submission goes through the same checks and human review.

---

## Choosing a Service

**Q: I am a complete beginner. Where do I start?**

A: See the [Quick Start Guide](QUICKSTART.md). In short:
- Want to *paper-trade* U.S. stocks with code → **Alpaca**
- Want to *backtest* Python strategies → **Backtrader** or **vectorbt**
- Want *free crypto data* → **CoinGecko** API
- Want *free market data* for research → **Yahoo Finance** (via `yfinance`) or **Alpha Vantage**

**Q: I need real-time data. What's the cheapest option?**

A: It depends on the asset class:
- **U.S. equities**: Alpaca (free plan streams real-time IEX data; full consolidated SIP data is paid), Massive (check which plan includes real-time rather than delayed data), or Interactive Brokers (market-data subscriptions on a funded account)
- **Crypto**: Binance, Bybit, OKX — all provide real-time WebSocket feeds at no cost
- **Forex**: OANDA demo account includes real-time FX data
- **Global macro**: Trading Economics (from $22/month)

**Q: Which broker has the best API for algorithmic trading?**

A: There is no single "best" — it depends on your jurisdiction, assets, and latency requirements:
| If you need... | Consider... | Caveat |
|---|---|---|
| Lowest commissions + global access | Interactive Brokers | Steep learning curve; API is powerful but verbose |
| Simple U.S. equities automation | Alpaca | Limited to U.S. markets |
| FX + CFDs | OANDA, cTrader | Regional restrictions apply |
| Options-focused | tastytrade | U.S.-only |
| Crypto multi-exchange | CCXT | You still manage exchange-specific risks |

**Q: Is there a free way to get institutional-grade data?**

A: Not truly "institutional-grade" for free, but several providers offer generous free tiers:
- **Databento** — free signup credits for exchange-sourced data
- **Nasdaq Data Link** — many free datasets
- **FRED** (Federal Reserve) — free U.S. macro data (access via direct API or through a provider)
- **DeFiLlama** — completely free DeFi analytics
- **GDELT** — free global news/event datasets

---

## Technical

**Q: Do I need to know Python?**

A: No, but it helps: most libraries and SDKs in this list support Python first. Many services also provide:
- **Go** SDKs (Finnhub, Twelve Data, Binance, CCXT)
- **JavaScript/TypeScript** (TradingView charts, Plotly, ECharts)
- **PHP** (Finnhub, CCXT, some crypto exchange wrappers)
- **C#** (QuantConnect LEAN engine)

**Q: What's the difference between REST and WebSocket APIs?**

A: | | REST | WebSocket |
|---|---|---|
| **Direction** | Request-response (you ask, server answers) | Bi-directional (server pushes data to you) |
| **Use case** | Historical data, placing orders, account info | Real-time price feeds, live order book updates |
| **Rate limits** | Usually stricter | Often more permissive for subscriptions |
| **Complexity** | Simpler to implement | Requires connection management, reconnection logic |

For most retail algo-trading, REST is sufficient. WebSocket becomes critical for high-frequency or market-making strategies.

**Q: What are testnet / paper trading / sandbox environments?**

A:
- **Paper trading** — Simulated trading with real market data but fake money. No real orders hit the market.
- **Testnet / Sandbox** — A separate API environment with fake data and fake money, used for integration testing.
- **Dry-run** — Some frameworks (e.g., Freqtrade) can run against live exchange APIs but without placing real orders.

**Always test on paper/testnet before going live.**

---

## Pricing & Licensing

**Q: Why are some prices marked "contact sales"?**

A: Enterprise or institutional data providers rarely publish fixed prices because costs depend on:
- Data depth (top-of-book vs. full order book)
- Historical lookback required
- Redistribution rights
- Number of users / API keys
- Exchange fees passed through

"Contact sales" does **not** mean the service is expensive — it means pricing is negotiated.

**Q: What hidden costs should I watch for?**

A:
1. **Exchange fees** — Some data providers pass through exchange licensing fees separately
2. **Market data subscriptions** — Interactive Brokers charges separately for real-time data
3. **Rate limit overages** — Exceeding free tier limits can trigger unexpected bills
4. **WebSocket premium** — Some providers (e.g., CCXT Pro) charge for WebSocket access
5. **Redistribution restrictions** — Using data in a public app or commercial product often requires a more expensive license

**Q: Can I use open-source tools commercially?**

A: Depends on the license:
- **MIT / BSD / Apache 2.0** — Generally yes, with attribution
- **LGPL** (e.g., NautilusTrader) — Yes, but modifications to the library itself must be open-sourced
- **GPL** — Your entire project may need to be open-sourced if you link to the library
- **Source-available / BSL** (e.g., some Redis distributions) — Check current terms; may have restrictions

---

## Data Quality

**Q: What's the difference between adjusted and unadjusted prices?**

A: **Adjusted prices** account for corporate actions (splits, dividends, spin-offs) so that historical charts reflect true returns. **Unadjusted prices** show the actual traded price at the time. For backtesting, you almost always want adjusted prices. Always verify which one a provider delivers.

**Q: How do I handle survivorship bias?**

A: Survivorship bias occurs when your dataset only contains companies that are *still alive*, ignoring delisted ones. This inflates backtested returns. To mitigate:
- Use providers with **delisted ticker coverage** (e.g., Databento, Massive)
- Maintain a **point-in-time** database of ticker changes
- Be explicit about this limitation in your research

**Q: What is look-ahead bias?**

A: Using information in a backtest that would not have been available at the decision time. Common examples:
- Using **end-of-day** data before the market closes
- Using **revised** economic data instead of **initial release**
- Using **full-sample** mean/variance in a rolling strategy

Always model **event time** — the moment information actually becomes available.

---

## Security

**Q: How do I safely store API keys?**

A: **Never hardcode API keys in your scripts.**

Best practices:
1. Use environment variables (`os.environ['API_KEY']`)
2. Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, 1Password CLI)
3. Use `.env` files that are **gitignored**
4. Rotate keys regularly
5. Use **IP whitelisting** where available
6. Use **read-only** keys for data-only workflows
7. Enable **2FA** on all exchange accounts

**Q: What permissions should I give API keys?**

A: Principle of least privilege:
| Workflow | Minimum Permissions |
|---|---|
| Data collection only | Read-only market data |
| Paper trading | Trading (simulated) + read |
| Live trading (conservative) | Spot trading + read, no withdrawals |
| Live trading (full) | Trading + read, withdrawals only via manual approval |

Never enable **withdrawal** permissions on API keys used by automated systems unless absolutely necessary.

**Q: A listed link looks like a scam or leads somewhere unexpected. What should I do?**

A: Don't enter credentials or connect a wallet. Report it **privately** as described in [SECURITY.md](SECURITY.md); confirmed malicious links are removed within 24 hours. The maintainers will never DM you, ask for API keys or seed phrases, or announce tokens or airdrops; anyone doing so is impersonating us.

---

## Contributing

**Q: How do I suggest a new service?**

A: Fill in the [Add a service](https://github.com/lentrade/trading-awesome/issues/new?template=new-entry.yml) form. A bot checks the form, your account, and the links, then opens a pull request that a maintainer reviews. Corrections go through the [Update an entry](https://github.com/lentrade/trading-awesome/issues/new?template=update-entry.yml) form or a pull request that edits the entry's file in `data/entries/`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the details.

**Q: Why was my submission or pull request closed automatically?**

A: The most common reasons:
- Your GitHub account is younger than **90 days** (30 days for updates) and you have no merged contribution here yet
- You already have an open submission, or reached the limit of 3 submissions in 30 days
- A first-time contributor opened a pull request that adds an entry directly; new entries go through the form
- The service's domain was registered less than 90 days ago

The bot's comment says which rule applied. If you think it is a mistake, reply on the issue or pull request and a maintainer will review it manually.

**Q: I represent a listed company. Can I update our entry?**

A: Yes, with the update form or a pull request. Disclose your affiliation and link an official source. Moving the entry to a different domain needs evidence that the new domain belongs to your organization; see [link and domain changes](CONTRIBUTING.md#link-and-domain-changes).

**Q: Why is my favorite tool not on the list?**

A: Possible reasons:
- It may not have a public API or active open-source repository
- It may have been deprioritized due to maintenance concerns
- It may be covered by a more general entry (e.g., CCXT covers many individual exchange wrappers)
- It does not yet meet two of the [editorial criteria](CONTRIBUTING.md#what-we-list)

Feel free to open an issue with justification.

---

## Legal & Regulatory

**Q: Can I legally use these APIs for automated trading in my country?**

A: **This list does not provide legal advice.** Regulations vary dramatically:
- **U.S.** — SEC, CFTC, and FINRA rules apply; pattern-day-trader rules for equities; accredited-investor requirements for some products
- **EU / UK** — MiFID II, GDPR (for data handling), ESMA leverage limits on CFDs
- **Other jurisdictions** — Check local securities and data-protection laws

Consult a qualified attorney before deploying automated trading systems.

**Q: Is the data on this list allowed for commercial use?**

A: Every provider has different terms. "Free tier" does **not** automatically mean "commercial use allowed." Always read the provider's Terms of Service, especially:
- Redistribution restrictions
- Display requirements (attribution, delayed vs. real-time labeling)
- Derivative works clauses

---

## Troubleshooting

**Q: My API requests are being rate-limited. What do I do?**

A:
1. Check the provider's rate-limit documentation (usually measured in requests/second or requests/minute)
2. Implement **exponential backoff** with jitter
3. Use **WebSocket** feeds instead of polling REST endpoints
4. Cache responses when the data doesn't change frequently
5. Consider upgrading to a paid plan

**Q: My backtest results look too good. What am I doing wrong?**

A: Common culprits:
- **Look-ahead bias** — using future information
- **Survivorship bias** — only testing on currently-listed assets
- **Overfitting** — too many parameters relative to data points
- **Ignoring transaction costs** — commissions, slippage, market impact
- **Unrealistic liquidity assumptions** — assuming you can trade unlimited size at the last price

See [section 8, Backtesting engines & trading frameworks](README.md#8-backtesting-engines--trading-frameworks), for tools that help mitigate these issues.

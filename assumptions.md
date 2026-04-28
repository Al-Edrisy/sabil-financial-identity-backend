# Salam Hack 2026: Sandbox Assumptions

Welcome to **Salam Hack**! To ensure you focus on building innovative Fintech prototypes rather than navigating complex legal frameworks, we have established the following "Sandbox Assumptions." Treat these points as immutable facts for the duration of the hackathon.

---

## 🏛️ General Regulatory Safe Harbor
* **The Virtual License:** Assume your startup operates under a **Central Bank Regulatory Sandbox License**. You have full legal permission to move funds and hold deposits for the duration of the hackathon.
* **The "Verified User" Rule:** Assume all users in your system have already passed **KYC (Know Your Customer)** and **AML (Anti-Money Laundering)** checks.
* **Zero Liability:** Assume all transactions are pre-authorized. You do not need to build complex dispute resolution or fraud-flagging systems.

---

## 🌙 Sharia-Compliance & Ethical Finance
* **Pre-Approved Architecture:** Assume your product architecture and logic have already been audited and cleared by a **Sharia Advisory Board**.
* **The "Halal" Filter:** Assume all merchant and transaction data provided or simulated has been pre-screened. You do not need to build industry-blocking logic (e.g., alcohol, gambling) unless it is your core feature.
* **Interest vs. Profit:** Treat all financial returns as **Profit-Sharing** (Musharaka/Mudarabah) rather than Interest (Riba). Assume the underlying interest-free contracts are legally active.
* **Zakat & Purification:** Assume "Zakat-eligible" assets are already flagged in your data. Assume "incidental" non-compliant income is automatically identified for purification/charity.

---

## 🚀 Track-Specific Assumptions

### Track 1: Sending & Receiving Money
* **Fixed FX Rates:** To avoid integrating live FX feeds, use a fixed "Hackathon Rate" (e.g., `1 USD = 3.67 AED` or `3.75 SAR`).
* **Instant Settlement:** Assume cross-border settlements happen instantly. You do not need to account for the typical 2-3 day delay of traditional banking rails.
* **Pre-Funded Liquidity:** Assume your "Remittance Hub" has pre-funded liquidity pools available in every destination country.

### Track 2: Financial Tools for Freelancers & Small Businesses
* **Open Banking Access:** Assume every bank in the region provides a **Read/Write Open Banking API**. You can pull transaction history and push payments seamlessly.
* **Tax Compliance:** Assume the "Tax Engine" for VAT or local business taxes is a black box that always provides the correct calculation. Focus on the UI/UX of the interaction.

### Track 3: Understanding & Managing Money
* **The Source of Truth:** Your backend database is legally recognized as a digital wallet. You do not need to hold "real" money in an escrow account.
* **Automatic Categorization:** Assume all transaction data comes "pre-tagged" (e.g., a grocery transaction is already labeled as "Food & Dining").
* **Seamless Funding:** Assume users can top up their digital wallets from any local debit card with 0% transaction fees.

---

## 🛠️ Technical Mocking Guidelines

> **Note to Participants:** We are judging **Innovation, User Experience, and Technical Implementation.**
>
> Since no external banking APIs are provided, you are encouraged to:
> 1. Use **Hardcoded JSON objects** to simulate bank responses.
> 2. Focus on the **"Golden Path"** (the perfect transaction flow).
> 3. Avoid building "utility" screens like 'Forgot Password' or 'Upload Passport' unless they are part of your unique innovation.

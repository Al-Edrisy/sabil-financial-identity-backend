# Sabil — Financial Identity Backend

![License](https://img.shields.io/github/license/Al-Edrisy/sabil-financial-identity-backend)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=fastapi&logoColor=white)
![Status](https://img.shields.io/badge/status-MVP-orange.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

**Sabil Backend** is a scalable FastAPI-based fintech API designed to power a unified **Financial Identity (Fin-ID)** system for emerging markets.

It enables users to create a portable financial identity, complete digital verification (KYC), generate AI-driven credit scores, and simulate cross-border transactions.

---

## 🚀 Key Features

* 🔐 **Authentication**

  * Firebase Authentication (Google & Email)
  * Secure token verification

* 🪪 **KYC (Know Your Customer)**

  * ID document scanning (OCR)
  * Face verification (AI-based)
  * Structured identity extraction

* 🧠 **AI Credit Scoring**

  * Financial behavior analysis
  * Risk scoring (0–100)
  * Explainable scoring factors

* 💸 **Cross-Border Payment Simulation**

  * Wallet-based transactions
  * FX conversion (mock rates)
  * Transaction lifecycle tracking

* 👥 **Recipient Management**

  * Save and manage transfer recipients

* 🤖 **AI Financial Assistant**

  * Arabic-first conversational assistant
  * Personalized financial insights

* 🔄 **Real-Time Updates**

  * WebSocket support for transactions and chat

---

## 🧱 Tech Stack

* **Backend:** FastAPI (Python)
* **Database:** PostgreSQL
* **ORM:** SQLAlchemy
* **Authentication:** Firebase Auth
* **AI & KYC:** OpenCV, EasyOCR, DeepFace
* **Validation:** Pydantic
* **Realtime:** WebSockets
* **Deployment:** Docker

---

## 🏗️ Architecture

* Monolithic backend (MVP)
* Layered architecture:

  * API Layer
  * Service Layer
  * AI Layer
  * Data Layer
* Stateless design for scalability

---

## 🎯 Project Vision

Sabil is not just a wallet.

It is a **Digital Financial Identity Infrastructure** that enables trust, access, and financial inclusion across borders.

---

## ⚠️ MVP Disclaimer

This project is built for a hackathon sandbox environment:

* No real banking integrations
* Payments are simulated
* KYC is simplified
* AI models are lightweight

---

## 📌 Future Improvements

* Real payment gateway integration
* Advanced fraud detection
* Full KYC compliance (AML, liveness)
* Microservices architecture

---
fintech
fastapi
financial-identity
kyc
ai-scoring
credit-score
cross-border-payments
firebase-auth
postgresql
python-backend
digital-wallet
remittance
open-banking
---

## 📄 License

MIT License

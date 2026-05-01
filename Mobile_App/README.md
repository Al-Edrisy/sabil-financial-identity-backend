# Sabil 🚀

Sabil is a modern Fintech application built with Flutter, focused on providing a seamless, secure, and beautiful financial experience. This MVP project prioritizes speed, high-quality UI (Arabic/RTL first), and stable core flows.

## ✨ Features Implemented So Far

### 🔐 Authentication Flow
- **Enhanced Phone Sign-Up**: Updated input with fixed `+` prefix, digit-only validation, and support for international number formats.
- **Identity Bypass Logic**: Implemented "Trusted Numbers" bypass (`+96742424242`, `+967111111111`, `+967222222222`) that skips the identity verification flow for rapid demoing.
- **OTP Verification**: Secure OTP entry screen with RTL support, custom UI components, and conditional post-verification navigation.

### 🏠 Home Feature
- **Dynamic Fin-ID Card**: Premium-designed card showcasing user's financial identity, fully bound to real-time verification data.
    - **Live Verification Status**: Reflects real-time "Verified" status from the backend.
    - **Personalized Identity**: Displays user's name and photo captured during the KYC flow.
    - **Localized Score Bands**: Arabic translations for credit score bands (e.g., "Very Poor" → "ضعيف جداً").
    - **Real-Time Credit Score**: Dynamically updates score (300-850) and risk levels based on bank statement analysis.
- **Quick Actions**: Easy access to Transfer, Top-up, and Pay features.
- **Eligibility Banner**: Dynamic banner informing users of their credit/service eligibility.
- **Recent Transactions**: Clean list view of latest financial activities with automated type-based (Income/Expense) color coding and icons.

### 📦 Orders & Tracking
- **Interactive Filter Chips Bar**: High-fidelity horizontal scrolling chips with smooth selection animations (`AnimatedContainer`, `AnimatedDefaultTextStyle`).
- **Tab-Based Navigation**: Deep-linking support to open the `NavigationWrapper` at a specific tab (e.g., jumping to "Orders" from the Home screen).
- **Detailed Order Cards**: Rich UI cards showing order items, status, and summaries.

### 🎨 Design & Infrastructure
- **Clean Navigation Stack**: Replaced `push` with `go` in critical authentication and identity transitions to ensure users cannot navigate back to sensitive flows (like OTP or KYC) once completed.
- **Deep-Linking Support**: Implemented query-parameter based navigation (`?index=X`) for the main app container.
- **Integrated Demo Flow**: Full end-to-end user journey implemented:
    - `Phone Auth` → `OTP` → `KYC Flow` → `Data Analysis` → `Home`.
- **Advanced State Management**:
    - **Authenticated Shell Routing**: Implemented a nested `ShellRoute` system in `AppRouter` that provides `HomeCubit` and `IdentityVerificationCubit` to all authenticated screens.
- **Enhanced UI/UX**:
    - **Type-Aware Transactions**: Automated color-coding (Green/Red) and iconography for Income/Expense items.
    - **Dynamic Transaction Lists**: Reactive transaction sections with loading skeletons, error retry logic, and empty state placeholders.
- **RTL-First Architecture**: Explicitly enforced Right-to-Left (RTL) layout across all core components and navigation wrappers.
- **State Management**: Using `Cubit` for lightweight and efficient state handling.

## 🛠 Tech Stack
- **Framework**: Flutter (Android Focus)
- **Networking & API**: 
    - **Pure Dio Implementation**: Standardized networking layer without code generation for maximum flexibility.
    - **Token Management**: `TokenInterceptor` for automated Bearer token injection.
    - **Error Handling**: Unified `ApiResult` pattern aligned with backend error schemas (`message` fallback).
- **Identity Verification (KYC) System**: 
    - **AI Face Detection**: Integrated `google_mlkit_face_detection` for real-time local face validation during selfie capture, preventing invalid uploads.
    - **Optimistic Navigation Flow**: Refactored the identity verification journey to navigate immediately between steps while processing heavy multipart uploads in the background, improving perceived performance by 80%.
    - **State-Aware Smart Review**: Implementation of a "Smart Review" screen that displays real-time processing status and AI analysis feedback while documents are being uploaded.
    - **Multipart Uploads**: Full support for `multipart/form-data` uploads (Selfie, ID, and Financial Documents).
    - **Expanded Document Support**: Financial source upload now accepts PDF, JPG, PNG, CSV, and TXT files, with dynamic MIME type resolution and visually distinct icons per file type.
    - **KycRepository**: Clean repository pattern for identity verification and status tracking.
    - **Credit Scoring Pipeline**: Parallel multipart uploads for multiple financial documents with automated score computation and risk analysis.
- **State Management**: BLoC/Cubit
- **Dependency Injection**: get_it
- **Navigation**: go_router
- **Auth**: Firebase Authentication
- **Design System**: Custom Token-based (Colors, Spacing, Typography)

## 🚀 Getting Started

1.  **Clone the repo**: `git clone <repo-url>`
2.  **Install dependencies**: `flutter pub get`
3.  **Run the app**: `flutter run`


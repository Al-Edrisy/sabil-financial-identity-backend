import json

def get_description(path, method, default_summary):
    descriptions = {
        "/api/v1/health": "### Health Check\n\nChecks the operational status of the Sabil Backend API. It ensures that the database and external services are functioning properly.\n\n**Expected Response:** HTTP 200 OK with `{'status': 'ok'}`",
        "/api/v1/auth/send-otp": "### Send OTP (Phone Authentication)\n\nInitiates the phone number verification process by sending a One-Time Password (OTP) to the user's phone.\n\n**Usage:** Call this before `verify-otp`. It handles rate limiting and prevents spam.",
        "/api/v1/auth/verify-otp": "### Verify OTP\n\nVerifies the One-Time Password sent to the user's phone. Upon successful verification, it returns the authentication tokens necessary for subsequent API calls.",
        "/api/v1/auth/login": "### User Login\n\nAuthenticates an existing user and issues JWT Access Tokens. \n\n**Notes:** This requires either a valid phone/password combination or Firebase authentication.",
        "/api/v1/users/me": "### Get Current Profile\n\nRetrieves the currently authenticated user's profile information. \n\n**Headers:** Requires `Authorization: Bearer <token>`.",
        "/api/v1/users/me/onboarding-status": "### Get Onboarding Status\n\nRetrieves the user's current step in the onboarding flow (e.g., pending phone verification, pending KYC, or fully verified).",
        "/api/v1/users": "### List or Create Users\n\nAdministrative endpoint to list all users, or create a new user profile depending on the HTTP method.",
        "/api/v1/users/{user_id}": "### Get User Details\n\nFetch detailed profile information for a specific user. Usually restricted to Admin or the user themselves.",
        "/api/v1/wallet/balance": "### Check Wallet Balance\n\nRetrieves the current available balance for the authenticated user's digital wallet.",
        "/api/v1/wallet/transfer": "### Transfer Funds\n\nTransfers money from the authenticated user's wallet to another user's wallet.\n\n**Important:** Ensure sufficient balance exists prior to transfer. The transaction is atomic.",
        "/api/v1/wallet/withdraw": "### Withdraw Funds\n\nInitiates a withdrawal from the digital wallet to a linked external bank account or card.",
        "/api/v1/wallet/history": "### Wallet Transaction History\n\nFetches a paginated list of all incoming and outgoing transactions for the current user's wallet.",
        "/api/v1/wallet/transactions/{transaction_id}": "### Transaction Details\n\nFetches metadata and detailed status for a specific transaction.",
        "/api/v1/wallet/topup": "### Wallet Top-up\n\nAdds funds to the user's digital wallet using an external payment method (e.g. Stripe/Credit Card).",
        "/api/v1/kyc/verify": "### Submit KYC Documents\n\nUploads identity documents (e.g., ID Card, Passport) and a selfie for automated Know Your Customer (KYC) verification.\n\n**Process:** Uses AI/OCR to extract data and match the face. Returns `VERIFIED` if successful, or `PENDING` if it requires manual admin review.",
        "/api/v1/kyc/resubmit": "### Resubmit KYC\n\nAllows the user to re-upload documents if their previous KYC attempt was rejected.",
        "/api/v1/kyc/status": "### Check KYC Status\n\nRetrieves the current status of the user's identity verification (`PENDING`, `VERIFIED`, `REJECTED`, or `EXPIRED`).",
        "/api/v1/kyc/history": "### KYC History\n\nFetches all past KYC verification attempts and their outcomes.",
        "/api/v1/kyc/debug-ocr": "### Debug OCR\n\nTesting endpoint used to evaluate the OCR extraction performance on uploaded documents without committing data to the database.",
        "/api/v1/admin/kyc/list": "### [Admin] List KYC Records\n\nFetches all KYC records across the platform. Useful for admin dashboards to find `PENDING` records requiring manual review.",
        "/api/v1/admin/kyc/{user_id}/review": "### [Admin] Review KYC\n\nAllows an admin to manually `APPROVE` or `REJECT` a pending KYC application. \n\n**Body Parameters:** Admin notes and the final decision.",
        "/api/v1/credit/debug-ocr": "### Debug Credit OCR\n\nTesting endpoint for debugging the extraction of data from financial statements.",
        "/api/v1/credit/currencies": "### Supported Currencies\n\nReturns a list of all fiat currencies supported by the credit scoring engine.",
        "/api/v1/credit/upload": "### Upload Financial Statements\n\nUploads bank statements or other financial documents. The system parses these files to categorize transactions and prepare a credit profile.",
        "/api/v1/credit/score": "### Get Credit Score\n\nCalculates and retrieves the user's Sabil Financial Credit Score based on their verified financial history.",
        "/api/v1/credit/transactions/review": "### Review Pending Transactions\n\nFetches parsed financial transactions that require user verification or categorization.",
        "/api/v1/credit/transactions": "### User Transactions\n\nLists all the parsed and categorized transactions associated with the user's credit profile.",
        "/api/v1/credit/transactions/{transaction_id}/correct": "### Correct Transaction\n\nAllows a user to manually correct the category or amount of a mis-parsed transaction.",
        "/api/v1/admin/credit/list": "### [Admin] List Credit Scores\n\nLists credit score details for all users. Used for platform-wide risk assessment.",
        "/api/v1/admin/credit/users/{user_id}/transactions": "### [Admin] View User Transactions\n\nAllows an admin to audit the parsed financial transactions of a specific user.",
        "/api/v1/admin/credit/users/{user_id}/rescore": "### [Admin] Force Credit Rescore\n\nManually triggers the credit scoring algorithm to recalculate a user's score based on the latest transaction data.",
        "/api/v1/admin/credit/review-queue": "### [Admin] Credit Review Queue\n\nFetches transactions flagged by the system as anomalous or requiring manual admin categorization.",
        "/api/v1/admin/credit/transactions/{transaction_id}/resolve": "### [Admin] Resolve Transaction Anomaly\n\nAllows an admin to manually resolve and categorize a flagged transaction."
    }
    
    if path in descriptions:
        return descriptions[path]
    return f"### {default_summary}\n\nEndpoint for {path}"

def main():
    with open("Sabil_Postman_Collection.json", "r") as f:
        spec = json.load(f)
        
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            summary = details.get("summary", "")
            
            # Enrich description
            details["description"] = get_description(path, method, summary)
            
            # Format the summary to be very clean (this becomes the request name in Postman)
            if not summary:
                details["summary"] = f"{method.upper()} {path}"

    with open("Sabil_Enriched_OpenAPI.json", "w") as f:
        json.dump(spec, f, indent=2)

if __name__ == "__main__":
    main()

# QuickBooks Online API Commands Reference

## Overview

This document provides a comprehensive list of QuickBooks Online API entities and operations available for automation. All endpoints are accessed via the base URL pattern:

**Production**: `https://quickbooks.api.intuit.com/v3/company/{companyID}/{entity}`
**Sandbox**: `https://sandbox-quickbooks.api.intuit.com/v3/company/{companyID}/{entity}`

## Authentication

All requests require OAuth 2.0 Bearer token in the Authorization header:

```text
Authorization: Bearer {access_token}
Accept: application/json
```

---

## Core Business Entities

### 📋 **Customer Management**

| Entity             | Create | Read | Update | Delete | Query | Batch |
|--------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Customer**       |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |
| **CustomerType**   |   Y    |  Y   |   Y    |   N    |   Y   |   N   |

*Customers can be made inactive but not deleted

### 🏢 **Vendor Management**

| Entity             | Create | Read | Update | Delete | Query | Batch |
|--------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Vendor**         |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |
| **VendorCredit**   |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |

*Vendors can be made inactive but not deleted

### 📦 **Items & Inventory**

| Entity                     | Create | Read | Update | Delete | Query | Batch |
|----------------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Item**                   |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |
| **InventoryQtyAdjustment** |   Y    |  Y   |   N    |   N    |   Y   |   N   |

*Items can be made inactive but not deleted

---

## Sales & Income Transactions

### 💰 **Sales Transactions**

| Entity              | Create | Read | Update | Delete | Query | Batch |
|---------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Invoice**         |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **SalesReceipt**    |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **Estimate**        |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **CreditMemo**      |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **RefundReceipt**   |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |

### 💸 **Payments & Credits**

| Entity              | Create | Read | Update | Delete | Query | Batch |
|---------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Payment**         |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **PaymentMethod**   |   Y    |  Y   |   Y    |   N    |   Y   |   N   |

---

## Expense & Purchase Transactions

### 💳 **Expense Transactions**

| Entity                  | Create | Read | Update | Delete | Query | Batch |
|-------------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Purchase**            |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **Bill**                |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **BillPayment**         |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **Expense**             |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **Check**               |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **CreditCardPayment**   |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |

---

## Chart of Accounts & Financial

### 📊 **Accounts**

| Entity        | Create | Read | Update | Delete | Query | Batch |
|---------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Account**   |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |

*Accounts can be made inactive but not deleted

### 🏦 **Banking**

| Entity             | Create | Read | Update | Delete | Query | Batch |
|--------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Deposit**        |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **Transfer**       |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |
| **JournalEntry**   |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |

---

## Payroll & Employees

### 👥 **Employee Management**

| Entity             | Create | Read | Update | Delete | Query | Batch |
|--------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Employee**       |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |
| **TimeActivity**   |   Y    |  Y   |   Y    |   Y    |   Y   |   Y   |

*Employees can be made inactive but not deleted

---

## Company Information & Settings

### 🏢 **Company Data**

| Entity             | Create | Read | Update | Delete | Query | Batch |
|--------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **CompanyInfo**    |   N    |  Y   |   Y    |   N    |   N   |   N   |
| **Preferences**    |   N    |  Y   |   Y    |   N    |   N   |   N   |

### 🏷️ **Classifications**

| Entity           | Create | Read | Update | Delete | Query | Batch |
|------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Class**        |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |
| **Department**   |   Y    |  Y   |   Y    |   N*   |   Y   |   Y   |

*Can be made inactive but not deleted

---

## Tax Management

### 📄 **Tax Entities**

| Entity           | Create | Read | Update | Delete | Query | Batch |
|------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **TaxAgency**    |   Y    |  Y   |   Y    |   N    |   Y   |   N   |
| **TaxCode**      |   Y    |  Y   |   Y    |   N    |   Y   |   N   |
| **TaxRate**      |   Y    |  Y   |   Y    |   N    |   Y   |   N   |
| **TaxService**   |   N    |  Y   |   N    |   N    |   N   |   N   |

---

## Terms & Exchange Rates

### 📋 **Business Terms**

| Entity     | Create | Read | Update | Delete | Query | Batch |
|------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **Term**   |   Y    |  Y   |   Y    |   N    |   Y   |   N   |

### 💱 **Currency**

| Entity             | Create | Read | Update | Delete | Query | Batch |
|--------------------|:------:|:----:|:------:|:------:|:-----:|:-----:|
| **ExchangeRate**   |   Y    |  Y   |   N    |   N    |   Y   |   N   |

---

## Utility Operations

### 🔍 **Query Operations**

- **Query All**: `GET /v3/company/{companyID}/{entity}`
- **Query by ID**: `GET /v3/company/{companyID}/{entity}/{id}`
- **Query with Filter**: `GET /v3/company/{companyID}/{entity}?query="SELECT * FROM {entity} WHERE {condition}"`

### 🔄 **Batch Operations**

- **Batch Request**: `POST /v3/company/{companyID}/batch`
- Supports multiple operations in a single request
- Maximum 25 operations per batch

### 📊 **Reports**

| Report Type          | Endpoint                     |
|----------------------|------------------------------|
| **BalanceSheet**     | `/reports/BalanceSheet`      |
| **ProfitAndLoss**    | `/reports/ProfitAndLoss`     |
| **CashFlow**         | `/reports/CashFlow`          |
| **TrialBalance**     | `/reports/TrialBalance`      |
| **GeneralLedger**    | `/reports/GeneralLedger`     |
| **CustomerSales**    | `/reports/CustomerSales`     |
| **ItemSales**        | `/reports/ItemSales`         |
| **VendorExpenses**   | `/reports/VendorExpenses`    |

---

## HTTP Methods & Operations

### ✅ **CRUD Operations**

| Operation  | HTTP Method | Endpoint Pattern                                       | Description             |
|------------|:-----------:|--------------------------------------------------------|-------------------------|
| **Create** | `POST`      | `/v3/company/{companyID}/{entity}`                     | Create new entity       |
| **Read**   | `GET`       | `/v3/company/{companyID}/{entity}/{id}`                | Get entity by ID        |
| **Update** | `POST`      | `/v3/company/{companyID}/{entity}`                     | Update existing entity  |
| **Delete** | `POST`      | `/v3/company/{companyID}/{entity}?operation=delete`    | Delete entity           |
| **Query**  | `GET`       | `/v3/company/{companyID}/{entity}`                     | Query entities          |

### 🔍 **Query Parameters**

- `query`: SQL-like query string
- `maxresults`: Limit number of results (default: 20, max: 1000)
- `startposition`: Pagination start position
- `orderby`: Sort field and direction
- `fetchAll`: Return all results (use with caution)

---

## Error Codes & Status

### 📊 **HTTP Status Codes**

- **200**: Success
- **400**: Bad Request (validation errors)
- **401**: Unauthorized (invalid token)
- **403**: Forbidden (insufficient permissions)
- **404**: Not Found
- **429**: Rate Limit Exceeded
- **500**: Internal Server Error
- **503**: Service Unavailable

### ⚠️ **Common Error Types**

- `ValidationFault`: Data validation errors
- `AuthenticationFault`: Authentication issues
- `AuthorizationFault`: Permission issues
- `SystemFault`: System-level errors

---

## Rate Limits & Best Practices

### 📈 **API Limits**

- **Rate Limit**: 500 requests per minute per app
- **Daily Limit**: 10,000 requests per day per app
- **Concurrent Requests**: 10 simultaneous requests

### 🎯 **Best Practices**

1. **Use Batch Operations** for multiple entities
1. **Implement Exponential Backoff** for rate limiting
1. **Cache Frequently Used Data** (customers, items, accounts)
1. **Use Sparse Updates** (only send changed fields)
1. **Handle Pagination** for large result sets
1. **Validate Data** before sending to API

---

## Useful Resources

- **Developer Portal**: [https://developer.intuit.com/app/developer/qbo](https://developer.intuit.com/app/developer/qbo)
- **API Explorer**: [https://developer.intuit.com/app/developer/qbo/docs/api/accounting/most-commonly-used](https://developer.intuit.com/app/developer/qbo/docs/api/accounting/most-commonly-used)
- **SDK Downloads**: [https://developer.intuit.com/app/developer/qbo/docs/develop/sdks-and-samples-collections](https://developer.intuit.com/app/developer/qbo/docs/develop/sdks-and-samples-collections)
- **Community Forum**: [https://help.developer.intuit.com/s/](https://help.developer.intuit.com/s/)

---

*Last Updated: September 22, 2025*
*Compatible with QuickBooks Online API v3*

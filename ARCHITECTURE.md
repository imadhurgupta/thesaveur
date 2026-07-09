# Technical Architecture Report: The Saveur Web Platform

This document provides a detailed overview of the system architecture, component design, database schema, core workflows, and deployment models for **The Saveur** e-commerce platform.

---

## 1. System Architecture Overview

The Saveur is a modern, high-performance e-commerce platform built with Flask, designed to be lightweight, modular, and portable. The architecture leverages **Redis** for query caching and **Celery + RabbitMQ** to offload blocking background tasks (like SMTP email delivery). It integrates multiple online gateways (Razorpay, PayPal) and relies on a local **SQLite 3** database for data persistence.

```mermaid
graph TD
    Client[User Browser]
    
    subgraph "Reverse Proxy & Load Balancing"
        Nginx[Nginx Container]
        Static[Static Assets CSS/JS/Images]
    end
    
    subgraph "Application Core"
        Flask[Gunicorn / Flask App]
        Redis[(Redis Cache)]
    end

    subgraph "Message Broker & Task Queue"
        RabbitMQ[RabbitMQ Broker]
        Celery[Celery Worker]
    end
    
    subgraph "Database & Storage"
        DB[(SQLite 3 Database)]
        Disk[(Local File System)]
    end

    subgraph "Third-Party Services"
        Google[Google OAuth 2.0]
        Razorpay[Razorpay API]
        PayPal[PayPal REST API]
        SMTP[SMTP Email Server]
    end

    Client <-->|HTTPS / Port 443| Nginx
    Nginx -->|Serves Directly| Static
    Nginx -->|Proxy Pass| Flask
    Flask <-->|Reads/Writes Cache| Redis
    Flask -->|Dispatches Tasks| RabbitMQ
    RabbitMQ -->|Consumes Tasks| Celery
    Celery -->|Queries DB| DB
    Celery -->|Sends Email| SMTP
    Flask <--> DB
    Flask -->|Uploads / Images| Disk
    Flask <--> Google
    Flask <--> Razorpay
    Flask <--> PayPal
```

---

## 2. Directory Structure

The codebase is organized into clean layers dividing frontend assets, server-side code, task queuing, and deployment manifests:

| Path | Description |
| :--- | :--- |
| `app.py` | Core Flask application containing routes, caching client, Celery task wrapper definitions, payment integrations, and business logic. |
| `database.py` | Database abstraction layer containing SQLite database path, connection setups, schema structures, and initial data seeder. |
| `api/index.py` | WSGI handler exposing the Flask application instance specifically for serverless hosting on Vercel. |
| `templates/` | HTML templates using Jinja2 syntax (e.g. `base.html`, catalog pages, admin dashboard views). |
| `static/` | Static folder containing client assets: `css/style.css` (custom design system), `js/main.js` (client interactions), and uploaded images. |
| `nginx/` | Reverse proxy settings, including SSL/HTTP2 configurations (`nginx.conf`) and local development proxy (`nginx_local.conf`). |
| `deploy.sh` | Bash script for one-command server deployment on Linux VPS. |
| `vercel.json` | Vercel deployment specifications mapping route rewrites to the WSGI backend wrapper. |

---

## 3. Core Component Details

### A. Backend Controller (`app.py`)
Powered by **Flask**, it operates as a consolidated monolithic server managing:
*   **Routing & Controller**: Administers user profiles, catalog filtering, wishlist, cart checkouts, and admin dashboard operations.
*   **Security & Validation**: Handles SHA-256 password hashing, email OTP verification, Razorpay signature checks, and PayPal REST OAuth authorization.
*   **State-wise Shipping engine**: Computes shipping rates dynamically based on the customer's state destination plus item-level surcharges.

### B. Redis Caching
Implements high-speed in-memory caching to optimize page load speeds:
*   **Target Queries**: Caches navbar categories (`nav_categories`) and catalog products/categories list (`all_products_list`, `nav_categories_list`) with a 1-hour TTL.
*   **Cache Invalidation**: Triggers cache keys deletion automatically upon product, category, or subcategory creations, updates, or deletions in the admin panel.
*   **Graceful Degradation**: Catches connection errors and falls back to direct database execution if Redis is offline.

### C. RabbitMQ & Celery Task Queue
Offloads time-consuming SMTP email operations to background threads:
*   **Broker & Worker**: Uses **RabbitMQ** as the message broker and a dedicated **Celery** worker container running the tasks.
*   **Tasks Defined**: OTP emails, login alerts, order invoices, shipping updates, and delivery alerts are dispatched asynchronously.
*   **Fallback Framework**: The dispatcher uses a try-except queue helper that routes tasks back to synchronous execution in the Flask thread if the broker is unavailable.

### D. Database Layer (`database.py`)
Relies on **SQLite 3** locally for data persistence:
*   **Zero Setup**: Automatically creates the SQLite database file (`thesaveur.db`) in the data directory and sets up the schemas on startup.
*   **Automatic Migrations & Seeding**: Handles initial data seeding for standard products, default categories, subcategories, carousel slides, location-wise shipping charges, and a default admin user dynamically if the tables are empty.

---

## 4. Database Schema

The database relies on a relational schema spanning 14 tables:

```mermaid
erDiagram
    users ||--o{ orders : "places"
    orders ||--|{ order_items : "contains"
    products ||--o{ order_items : "ordered-in"
    products ||--o{ product_images : "has-multiple"
    products ||--o{ reviews : "has"
    categories ||--o{ subcategories : "groups"
    
    users {
        string id PK
        string full_name
        string email UNIQUE
        string password_hash
        int is_admin
        string phone
        string shipping_address
        string city
        string state
        string zip_code
        timestamp created_at
    }

    products {
        string id PK
        string name
        string category
        string sub_category
        string description
        string image_filename
        real price
        int stocks
        int is_bestseller
        string unit
        real shipping_charge
        real gst_rate
        real discount_percent
    }

    orders {
        int id PK
        string user_id FK
        real total_amount
        string shipping_address
        string city
        string state
        string zip_code
        string payment_method
        string status
        string contact_name
        string contact_email
        string contact_phone
        string razorpay_order_id
        string razorpay_payment_id
        string razorpay_signature
        string paypal_order_id
        string paypal_payment_id
        real discount_amount
        string promo_code
        string order_number
        real shipping_charge
        timestamp created_at
    }

    order_items {
        int id PK
        int order_id FK
        string product_id FK
        int quantity
        real price
        real original_price
        real discount_percent
    }

    location_shipping_charges {
        int id PK
        string state UNIQUE
        real charge
    }
```

---

## 5. Core Workflows

### A. PayPal Verification Flow

This workflow illustrates how the client-side PayPal SDK coordinates checkout verification and capture with the Flask backend.

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer
    participant SDK as PayPal JS SDK
    participant Flask as Flask App (app.py)
    participant PP as PayPal API
    participant DB as Database
    participant Celery as Celery / RabbitMQ

    Customer->>Flask: Submit Cart & Details
    activate Flask
    Flask->>DB: Create Pending Order
    DB-->>Flask: Order ID
    Flask-->>Customer: Return Order Details & PayPal config
    deactivate Flask
    Customer->>SDK: Click PayPal / Card Button
    activate SDK
    SDK->>PP: Create PayPal Order
    PP-->>SDK: Order ID (paypal_order_id)
    SDK->>Customer: Render payment modal
    Customer->>SDK: Authorize payment
    SDK->>PP: Capture Authorization
    PP-->>SDK: Capture Approved
    SDK->>Flask: POST /checkout/verify-paypal (order_id, paypal_order_id)
    activate Flask
    Flask->>PP: Verify payment capture status
    PP-->>Flask: Payment Capture OK
    Flask->>DB: Update order status to "Processing" & decrement stock
    Flask->>Celery: Queue order invoice email task (async)
    Flask-->>SDK: Return verification success JSON
    deactivate Flask
    SDK->>Customer: Redirect to orders success page
    deactivate SDK
```

### B. Asynchronous Email Task Flow

This flow details how user alerts (OTPs, invoices) are executed via the message queue.

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Flask as Flask App (app.py)
    participant MQ as RabbitMQ Broker
    participant Worker as Celery Worker
    participant SMTP as SMTP Mail Server

    User->>Flask: Request Action (Signup / Checkout)
    activate Flask
    Flask->>Flask: Execute logic (Save DB)
    Flask->>MQ: Publish email payload task
    Note over Flask, MQ: If MQ connection fails, execute synchronously
    Flask-->>User: Return HTTP Response immediately (e.g. 200 OK)
    deactivate Flask

    MQ->>Worker: Consume email task
    activate Worker
    Worker->>SMTP: Connect & send SMTP MIME mail
    SMTP-->>Worker: Mail sent successfully
    deactivate Worker
```

---

## 6. Infrastructure & Native Deployment

The application is deployed natively on a VPS (Virtual Private Server) or local machine:

1.  **Nginx Reverse Proxy**: Terminates HTTPS traffic on port 443 and proxies requests to Gunicorn. Serves `/static/` assets directly for optimal performance.
2.  **Flask Web Server (Gunicorn)**: Binds to port 8000. Accesses `thesaveur.db` SQLite database file natively.
3.  **Redis Cache (Service)**: Runs locally or as a system service on port 6379 for caching.
4.  **RabbitMQ & Celery (Services)**: The RabbitMQ message broker service distributes tasks, and a background Celery worker process runs `celery -A app.celery_app worker --loglevel=info` to consume asynchronous SMTP mailing tasks.

---

## 7. Configuration Reference (`.env`)

Declare the following keys in the environment or `.env` file to configure caching, task queuing, and payment gateways:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SECRET_KEY` | *Required* | Key used to sign session cookies. |
| `DATA_DIR` | *App Directory* | Folder path where the SQLite database file (`thesaveur.db`) is stored. |
| `REDIS_URL` | `redis://localhost:6379/0` | URL connecting to the Redis database cache. |
| `CELERY_BROKER_URL` | *None* | Connection URL for RabbitMQ broker (e.g., `amqp://guest:guest@localhost:5672//`). |
| `CELERY_RESULT_BACKEND`| `rpc://` | Celery task result tracker backend. |
| `SMTP_SERVER` | *None* | Outgoing SMTP mail server host address. |
| `SMTP_PORT` | `587` | Outgoing SMTP port. |
| `SMTP_USER` | *None* | Email sender account username. |
| `SMTP_PASSWORD` | *None* | App-specific email SMTP password. |
| `PAYPAL_CLIENT_ID` | *None* | PayPal OAuth client ID. |
| `PAYPAL_CLIENT_SECRET` | *None* | PayPal OAuth client secret. |
| `PAYPAL_MODE` | `sandbox` | Operations mode (`sandbox` or `live`). |
| `PAYPAL_EXCHANGE_RATE_INR_TO_USD` | `0.012` | INR to USD currency rate. |
| `RAZORPAY_KEY_ID` | *None* | Razorpay API key ID. |
| `RAZORPAY_KEY_SECRET` | *None* | Razorpay API key secret. |

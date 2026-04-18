# Roadmap

## Done

- SQLite schema
- CLI commands
- Google Sheets integration
- item CSV import
- multiple suppliers per item
- web dashboard
- item list
- add/edit item screen
- stock count screen
- Little Shop request list
- Keele supplier shopping list

## Next

### 1. Record Transfers

Add a button on the Little Shop request list:

```text
Record transfer from Keele to Little Shop
```

This should create stock transactions so the database reflects what staff actually moved.

### 2. Edit Par Levels In The App

Add fields on the item edit page for:

- Keele par
- Little Shop par

This removes the need to update par levels through CSV.

### 3. Supplier Order Workflow

Add a way to turn the shopping list into an order record.

Possible states:

- draft
- ordered
- received
- cancelled

### 4. Receiving Deliveries

Add a web screen to record deliveries into Keele.

### 5. Waste And Adjustments

Add simple forms for:

- waste
- damage
- stock corrections

### 6. User Accounts

Add login and roles:

- staff
- manager
- admin

### 7. Postgres Migration

Move production data from SQLite to Postgres before the app becomes heavily multi-user.

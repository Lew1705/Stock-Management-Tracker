# Workflows

## Daily Stock Workflow

1. Count Little Shop stock.
2. Count Keele stock.
3. Save both counts in the web app.
4. Open the Little Shop request list.
5. Staff take stock from Keele to Little Shop.
6. Open the Keele shopping list.
7. Order supplier stock for Keele.

## Count Stock

Open:

```text
/counts
```

Choose:

- `Keele`
- `Little Shop`

Enter quantities and save.

## Little Shop Request List

Open:

```text
/request-lists
```

This is always:

```text
what staff need to take from Keele to Little Shop
```

It uses:

- Little Shop count
- Little Shop par levels
- Keele count

## Keele Shopping List

Open:

```text
/shopping-lists
```

This is always:

```text
what needs ordering from suppliers for Keele
```

It uses:

- Keele count
- Keele par levels
- Little Shop request need
- supplier details

## Item Management

Open:

```text
/items
```

You can:

- view items grouped by category
- add an item
- edit item details
- set suppliers and references

Par-level editing is currently handled through CSV import. A web par-level editor is a recommended next feature.

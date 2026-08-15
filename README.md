# Equipment Rental & Maintenance

## Overview

`x_equipment_rental` is a custom Odoo 19 Community module for managing the rental lifecycle of physical equipment such as excavators, generators, and scaffolding.

The module is built around native Odoo models where reuse is appropriate:

- `maintenance.equipment` is reused as the equipment catalog
- `maintenance.request` is reused for maintenance scheduling
- `sale.order` and `account.move` are used for commercial document generation

The current implementation covers the core equipment catalog, rental order model, workflow, availability checks, maintenance conflict handling, security groups, sales integration, and late return tracking.

## Implemented Features

### 1. Equipment Catalog

The equipment catalog extends Odoo's `maintenance.equipment` model instead of duplicating equipment data.

Added rental-specific fields:

- Daily Rental Rate
- Weekly Rental Rate
- Rental Status:
  - Available
  - Reserved
  - Rented
  - Maintenance

Reused native fields:

- Equipment Name
- Category
- Serial Number
- Purchase Date:
  - implemented by reusing `maintenance.equipment.effective_date`

### 2. Rental Orders

Custom business models:

- `x.rental.order`
- `x.rental.order.line`

Supported data:

- Customer
- Rental Start Date
- Rental End Date
- One or more equipment units
- Automatic total amount calculation

Pricing logic:

- Rentals shorter than 7 days use daily pricing
- Rentals of 7 days or longer use weekly pricing for full weeks and daily pricing for remaining days

### 3. Double Booking Prevention

Implemented safeguards include:

- overlap validation between active rental orders
- overlap validation between rentals and maintenance schedules
- confirmation-time row locking on equipment records using Odoo 19 locking APIs
- validation that works from model constraints, not only from the UI

### 4. Rental Workflow

Implemented states:

- Draft
- Confirmed
- Out
- Returned
- Invoiced
- Cancelled

Implemented workflow actions:

- Confirm
- Mark Out
- Return
- Mark Invoiced
- Cancel

Implemented rules:

- invalid transitions are blocked
- cancellation is allowed only from Draft and Confirmed
- at least one equipment line is required before confirmation

### 5. Maintenance Management

The module reuses `maintenance.request` instead of a custom maintenance model.

Supported behavior:

- equipment can be scheduled for maintenance
- scheduled maintenance blocks equipment availability
- maintenance requests cannot overlap active rentals for the same equipment

### 6. Late Return Handling

Implemented:

- overdue flag on rental orders
- overdue day count
- late fee amount
- actual return date
- configurable fixed late fee per day
- daily scheduled action to update overdue rentals

Current late fee model:

- `late_fee = overdue_days x configured late fee per day x equipment line count`

### 7. Sales Integration

On rental confirmation, the module can generate either:

- a Sales Order
- or a draft Customer Invoice

Configuration is handled in Settings.

Implemented:

- integration mode setting
- configurable rental service product
- fallback default rental service product provided by module data
- smart buttons to open generated commercial documents

### 8. Security

Defined groups:

- Rental User
- Rental Manager

Implemented security components:

- model access rights
- ownership-based record rules for rental orders and rental lines
- manager full-access rules for rental records
- multi-company rules for rental orders and rental lines

### 9. Availability Screen

Implemented wizard:

- Date Range
- Equipment Category

Behavior:

- returns only equipment available in the selected period
- checks both rental overlaps and maintenance overlaps
- uses batch search logic instead of one query per equipment

## Installation

### Dependencies

The module depends on:

- `base`
- `mail`
- `maintenance`
- `sale_management`
- `account`

### Steps

1. Copy the module into your custom addons path.
2. Restart the Odoo server.
3. Update the apps list.
4. Install or upgrade `x_equipment_rental`.

Example upgrade flow:

```bash
$PYTHON "$ODOO_BIN_PATH" -c "$ODOO_CONF_PATH" -d "$ODOO_DB_NAME" -u x_equipment_rental
```

If Python model code changes, restart Odoo before upgrading so the registry loads the updated fields and methods.

## Configuration

Go to:

- Sales
- Settings
- Equipment Rental

Available settings:

- Rental Sales Integration
- Rental Service Product
- Late Fee Per Day

## How To Review Quickly

A reviewer can validate the module with the following flow:

1. Open Equipment Rental > Equipment and create one equipment asset
2. Set Daily Rental Rate and Weekly Rental Rate
3. Create a rental order with one equipment line
4. Confirm the order and verify document generation
5. Create an overlapping rental and verify it is blocked
6. Create overlapping maintenance and verify rental blocking
7. Mark the rental Out, Returned, and Invoiced
8. Set a past rental end date and run the scheduled action to verify overdue behavior

## Design Decisions

### Reuse of Native Models

The module intentionally reuses native Odoo models where appropriate:

- `maintenance.equipment` for physical assets
- `maintenance.request` for maintenance scheduling
- `sale.order` and `account.move` for downstream commercial documents

This keeps the solution closer to Odoo conventions and avoids unnecessary duplication.

### Separate Rental Business Model

Rental operations are handled through a dedicated custom model instead of overloading Sales Orders directly.

Reason:

- the rental lifecycle is not the same as the sales lifecycle
- booking validation and maintenance conflicts are easier to enforce on a dedicated rental domain model
- sales and accounting integration remain downstream outputs of the rental process

### Pricing Strategy

The module uses:

- daily pricing for rentals under 7 days
- weekly pricing for full weeks
- daily pricing for remaining days after full weeks

This was chosen as a practical interpretation of the assessment requirement for durations above 7 days.

### Overlap Control Strategy

Conflict prevention combines:

- model constraints
- explicit validation methods
- equipment row locking on confirmation

This is more robust than relying on onchange or UI-only validation.

## Assumptions

- Rental dates are treated as date-based reservations, not hourly bookings
- Maintenance uses `schedule_date` and `schedule_end` from `maintenance.request`
- Commercial document generation happens automatically on rental confirmation
- The late fee is tracked on the rental order and is not yet automatically injected into already-generated sales orders or invoices

## Trade-Offs

- The solution prioritizes clear business logic and Odoo-native reuse over a deeper feature set
- The late fee model is intentionally simple: fixed fee per day per equipment line
- Sales/invoice generation uses a generic rental service product rather than one product per equipment asset

## Current Gaps

The module is not yet fully complete for a production-grade submission.

Known gaps:

- automated tests are not yet implemented
- demo data is not yet included
- README-backed installation is complete, but no migration script is included
- customer portal is not implemented
- PDF rental agreement is not implemented
- late fees are not yet synchronized back into already-generated sales orders or invoices

## What I Would Improve With More Time

- add automated test coverage for:
  - pricing
  - rental overlap validation
  - maintenance conflicts
  - workflow transitions
  - late return cron behavior
- add demo data for a five-minute reviewer walkthrough
- add a QWeb rental agreement report
- add optional late-fee propagation to generated invoices or sales orders
- improve multi-company testing depth
- add a migration example for a versioned field rename

## Optional Enhancements Status

- Customer Portal: not implemented
- PDF Rental Agreement using QWeb: not implemented
- Migration script demonstrating a field rename: not implemented

## Author

Mohammed Galal

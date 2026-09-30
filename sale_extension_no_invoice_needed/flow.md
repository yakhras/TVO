# Sale Extension - No Invoice Needed: algorithm

The buttons never write `invoice_status` directly. They write only the flag `no_invoice_needed`;
the ORM then recomputes `invoice_status` through `@api.depends` (sub-process **C**, shared by A and B).

## A) To Invoice -> No Invoice Needed  (`action_set_no_invoice_needed`)

```mermaid
flowchart TD
    S([Start]) --> A[Open Sales app]
    A --> B[Menu: To Invoice]
    B --> C["Menu: Orders to Invoice<br/>(list: invoice_status = 'to invoice')"]
    C --> D[/User selects one or more orders/]
    D --> G{"User in group<br/>Accounting / Administrator?"}
    G -- No --> X([End: button not shown])
    G -- Yes --> H[List header shows<br/>'Set No Invoice Needed' button]
    H --> I[/User clicks the button/]
    I --> L{{For each selected order}}
    L --> K{"invoice_status == 'to invoice'?"}
    K -- No --> SK[Skip order]
    K -- Yes --> KP[Keep order]
    SK --> N{More orders?}
    KP --> N
    N -- Yes --> L
    N -- No --> W["write(): no_invoice_needed = True<br/>on kept orders (one batch write)<br/><i>saves the flag only</i>"]
    W --> CC[["C) ORM dependency + recompute<br/>(see below)"]]
    CC --> P{{For each kept order}}
    P --> M["Post chatter message:<br/>'To Invoice' -> 'No Invoice Needed'"]
    M --> Q{More orders?}
    Q -- Yes --> P
    Q -- No --> E([End: orders leave 'Orders to Invoice'<br/>and appear under 'No Invoice Needed'])
```

## B) No Invoice Needed -> To Invoice  (`action_reset_to_invoice`)

```mermaid
flowchart TD
    S([Start]) --> B[Sales > To Invoice > No Invoice Needed]
    B --> D[/User selects one or more orders/]
    D --> G{"User in group<br/>Accounting / Administrator?"}
    G -- No --> X([End: button not shown])
    G -- Yes --> H[List header shows<br/>'Reset to To Invoice' button]
    H --> I[/User clicks the button/]
    I --> L{{For each selected order}}
    L --> K{"invoice_status == 'no_invoice_needed'?"}
    K -- No --> SK[Skip order]
    K -- Yes --> KP[Keep order]
    SK --> N{More orders?}
    KP --> N
    N -- Yes --> L
    N -- No --> W["write(): no_invoice_needed = False<br/>on kept orders (one batch write)<br/><i>saves the flag only</i>"]
    W --> CC[["C) ORM dependency + recompute<br/>(see below)"]]
    CC --> P{{For each kept order}}
    P --> M["Post chatter message:<br/>'No Invoice Needed' -> 'To Invoice'"]
    M --> Q{More orders?}
    Q -- Yes --> P
    Q -- No --> E([End: orders return to 'Orders to Invoice'])
```

## C) ORM dependency + recompute (triggered by the write in A or B)

```mermaid
flowchart TD
    W([write on no_invoice_needed]) --> D1["ORM looks up fields depending on 'no_invoice_needed'"]
    D1 --> D2{"Declared by<br/>@api.depends('no_invoice_needed')?"}
    D2 -- No --> Z(["invoice_status NOT marked:<br/>stays stale until state / lines change (bug)"])
    D2 -- Yes --> MK["Mark invoice_status of the written orders<br/>as 'to recompute'"]
    MK --> T["At flush (before the button call returns,<br/>or earlier if the field is read)"]
    T --> F["Call _compute_invoice_status()"]
    F --> SP["super(): core logic from order lines<br/>-> no / to invoice / invoiced / upselling"]
    SP --> L{{For each order}}
    L --> R{"no_invoice_needed == True<br/>and state == 'sale'?<br/>(locked orders are state 'sale')"}
    R -- Yes --> OV["invoice_status = 'no_invoice_needed'"]
    R -- No --> KC[Keep core value]
    OV --> N{More orders?}
    KC --> N
    N -- Yes --> L
    N -- No --> ST([Store invoice_status in DB])
```

Note on timing: C is lazy. In A/B it is drawn right after the write for clarity; in practice the
ORM may run it while the chatter loop runs or at the final flush, but always before the button's
transaction commits, so the stored status is correct when the list reloads.

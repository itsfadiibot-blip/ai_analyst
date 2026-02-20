# 07 — Safe Actions Framework

## Core Principle

**AI proposes. Humans approve. System executes.**

The AI must NEVER directly create, write, or unlink business records. All write operations follow a three-phase flow:

```
Phase 1: PROPOSE    → AI creates a proposal record with full details
Phase 2: APPROVE    → Human reviews, modifies if needed, and approves
Phase 3: EXECUTE    → System creates the actual business record (e.g., draft PO)
```

## Data Models

### `ai.analyst.action.proposal`

```
_name = 'ai.analyst.action.proposal'
_description = 'AI Action Proposal'
_order = 'create_date desc'
_inherit = ['mail.thread', 'mail.activity.mixin']   # chatter for discussion

Fields:
    name                Char            computed    "Proposal: {action_type} #{id}"
    sequence_ref        Char            readonly    Auto-sequence: AIPROP-0001

    # Context
    user_id             Many2one        res.users       Who initiated (requestor)
    company_id          Many2one        res.company     required
    workspace_id        Many2one        ai.analyst.workspace
    conversation_id     Many2one        ai.analyst.conversation
    message_id          Many2one        ai.analyst.message   Source AI message

    # What
    action_type         Selection       required
        'purchase_order'    — Create draft purchase order
        'stock_adjustment'  — Suggest inventory adjustment (future)
        'price_change'      — Suggest price change (future)
        'tag_assignment'    — Suggest product tag changes (future)

    description         Text            AI-generated explanation of the proposal
    reasoning           Text            AI reasoning / justification

    # Payload
    payload_json        Text            required    JSON: the structured action data
    payload_summary     Text            computed    Human-readable summary of payload
    line_count          Integer         computed    Number of lines in payload

    # State Machine
    state               Selection       required    default='draft'
        'draft'         — Proposed by AI, awaiting review
        'reviewed'      — Reviewed by user, modifications possible
        'approved'      — Approved, ready for execution
        'executed'      — Successfully executed
        'rejected'      — Rejected by approver
        'expired'       — Not acted upon within TTL
        'failed'        — Execution failed

    # Approval
    reviewed_by         Many2one        res.users
    reviewed_at         Datetime
    approved_by         Many2one        res.users
    approved_at         Datetime
    rejected_by         Many2one        res.users
    rejected_at         Datetime
    rejection_reason    Text

    # Execution
    executed_at         Datetime
    execution_result    Text            JSON: created record references
    target_record_ref   Char            e.g. "purchase.order,42"
    error_message       Text

    # TTL
    expires_at          Datetime        default=create_date + 7 days
```

### `ai.analyst.action.proposal.line`

```
_name = 'ai.analyst.action.proposal.line'
_description = 'Proposal Line Item'

Fields:
    proposal_id         Many2one        ai.analyst.action.proposal  required
    sequence            Integer         default=10

    # Product Reference
    product_id          Many2one        product.product
    product_tmpl_id     Many2one        product.template    related
    product_name        Char            related
    default_code        Char            related

    # Action-specific fields
    quantity            Float
    unit_price          Float
    currency_id         Many2one        res.currency
    uom_id              Many2one        uom.uom
    supplier_id         Many2one        res.partner     domain=[('supplier_rank','>',0)]

    # From AI analysis
    current_stock       Float           readonly
    velocity_daily      Float           readonly
    coverage_days       Float           readonly
    confidence          Selection       [('high','High'),('medium','Medium'),('low','Low')]
    reasoning           Text            Per-line explanation

    # User edits
    user_quantity       Float           User can override AI suggestion
    user_notes          Text
    is_excluded         Boolean         default=False   User can exclude lines
```

### `ai.analyst.action.execution`

```
_name = 'ai.analyst.action.execution'
_description = 'Action Execution Log'

Fields:
    proposal_id         Many2one        ai.analyst.action.proposal  required
    executed_by         Many2one        res.users       required
    executed_at         Datetime        required

    # Result
    success             Boolean
    target_model        Char            e.g. "purchase.order"
    target_id           Integer         e.g. 42
    target_ref          Char            e.g. "PO00042"
    result_json         Text            Full execution details
    error_message       Text

    # Audit
    lines_processed     Integer
    lines_skipped       Integer         (excluded by user)
    total_value         Float
    currency_id         Many2one        res.currency
```

## Proposal Creation Flow (AI Side)

When the reorder suggestion tool returns results with an `actions` block:

```python
# In gateway, after tool returns actions:
for action in tool_result.get('actions', []):
    if action['type'] == 'create_proposal':
        self._create_proposal_from_tool_result(
            user=user,
            conversation=conversation,
            message=message,
            action_type=action['proposal_type'],
            tool_result=tool_result,
            data_key=action['data_key'],
        )

def _create_proposal_from_tool_result(self, user, conversation, message,
                                       action_type, tool_result, data_key):
    """Create a structured proposal from tool output."""
    rows = tool_result.get(data_key, [])
    if not rows:
        return

    # Build payload
    payload = {
        'action_type': action_type,
        'source_tool': tool_result.get('meta', {}).get('tool_name'),
        'source_params': tool_result.get('meta', {}).get('params_used'),
        'lines': rows,
    }

    proposal = self.env['ai.analyst.action.proposal'].create({
        'action_type': action_type,
        'user_id': user.id,
        'company_id': user.company_id.id,
        'workspace_id': conversation.workspace_id.id if conversation.workspace_id else False,
        'conversation_id': conversation.id,
        'message_id': message.id,
        'description': self._generate_proposal_description(action_type, rows),
        'reasoning': tool_result.get('meta', {}).get('formula', ''),
        'payload_json': json.dumps(payload, default=str),
        'expires_at': fields.Datetime.now() + timedelta(days=7),
    })

    # Create structured line items
    for row in rows:
        product = self.env['product.product'].search(
            [('default_code', '=', row.get('default_code'))], limit=1
        )
        if product:
            self.env['ai.analyst.action.proposal.line'].create({
                'proposal_id': proposal.id,
                'product_id': product.id,
                'quantity': row.get('suggested_qty_after_moq', row.get('suggested_qty', 0)),
                'unit_price': row.get('unit_cost', 0),
                'supplier_id': self._find_supplier(product),
                'current_stock': row.get('current_stock', 0),
                'velocity_daily': row.get('velocity_daily', 0),
                'coverage_days': row.get('coverage_days_current', 0),
                'confidence': row.get('confidence', 'medium'),
                'reasoning': row.get('reasoning', ''),
            })

    return proposal
```

## Approval Flow

### Step 1: Review (Optional)

The proposal appears in the **Proposals** menu and in the chat response as an action card.

```
Proposal Card in Chat:
┌─────────────────────────────────────────┐
│ 📋 Reorder Proposal AIPROP-0042        │
│ 35 items | Est. €24,500                 │
│ Based on: velocity analysis (30 days)   │
│                                         │
│ [Review & Edit]  [Quick Approve]        │
└─────────────────────────────────────────┘
```

Clicking **Review & Edit** opens the proposal form view where the user can:
- Modify quantities (`user_quantity` field)
- Exclude lines (`is_excluded` checkbox)
- Add notes
- Change supplier assignments
- View per-line AI reasoning

### Step 2: Approve

```python
def action_approve(self):
    self.ensure_one()
    if self.state not in ('draft', 'reviewed'):
        raise UserError("Cannot approve a proposal in state '%s'." % self.state)

    # Permission check: must have purchase manager group for PO proposals
    if self.action_type == 'purchase_order':
        if not self.env.user.has_group('purchase.group_purchase_manager'):
            raise AccessError("Only Purchase Managers can approve purchase proposals.")

    self.write({
        'state': 'approved',
        'approved_by': self.env.user.id,
        'approved_at': fields.Datetime.now(),
    })
    # DO NOT auto-execute. User must explicitly click "Execute".
```

### Step 3: Execute

```python
def action_execute(self):
    """Execute the approved proposal. Creates the actual business record."""
    self.ensure_one()
    if self.state != 'approved':
        raise UserError("Only approved proposals can be executed.")

    executor = self._get_executor(self.action_type)
    execution_log = executor.execute(self)
    return execution_log
```

### Purchase Order Executor

```python
class PurchaseOrderExecutor:
    """Creates a DRAFT purchase order from an approved proposal."""

    def execute(self, proposal):
        env = proposal.env
        lines = proposal.line_ids.filtered(lambda l: not l.is_excluded)

        if not lines:
            raise UserError("No lines to process (all excluded).")

        # Group lines by supplier
        supplier_groups = defaultdict(list)
        for line in lines:
            supplier = line.supplier_id
            if not supplier:
                raise UserError(f"No supplier for {line.product_name}. Assign suppliers first.")
            supplier_groups[supplier.id].append(line)

        created_pos = []
        for supplier_id, group_lines in supplier_groups.items():
            supplier = env['res.partner'].browse(supplier_id)

            po = env['purchase.order'].create({
                'partner_id': supplier.id,
                'company_id': proposal.company_id.id,
                'origin': proposal.sequence_ref,
                'notes': f"Generated from AI Proposal {proposal.sequence_ref}",
                # State is 'draft' by default — NOT confirmed
            })

            for line in group_lines:
                qty = line.user_quantity if line.user_quantity > 0 else line.quantity
                env['purchase.order.line'].create({
                    'order_id': po.id,
                    'product_id': line.product_id.id,
                    'product_qty': qty,
                    'price_unit': line.unit_price,
                    'product_uom': line.uom_id.id or line.product_id.uom_po_id.id,
                })

            created_pos.append(po)

        # Log execution
        execution = env['ai.analyst.action.execution'].create({
            'proposal_id': proposal.id,
            'executed_by': env.user.id,
            'executed_at': fields.Datetime.now(),
            'success': True,
            'target_model': 'purchase.order',
            'target_id': created_pos[0].id if len(created_pos) == 1 else 0,
            'target_ref': ', '.join(po.name for po in created_pos),
            'lines_processed': len(lines),
            'lines_skipped': len(proposal.line_ids) - len(lines),
            'total_value': sum(
                (l.user_quantity or l.quantity) * l.unit_price for l in lines
            ),
            'result_json': json.dumps({
                'purchase_orders': [{'id': po.id, 'name': po.name} for po in created_pos]
            }),
        })

        proposal.write({
            'state': 'executed',
            'executed_at': fields.Datetime.now(),
            'target_record_ref': f"purchase.order,{created_pos[0].id}" if created_pos else '',
        })

        # Audit log
        env['ai.analyst.audit.log'].create({
            'user_id': env.user.id,
            'company_id': proposal.company_id.id,
            'conversation_id': proposal.conversation_id.id,
            'event_type': 'action_executed',
            'summary': f"Executed proposal {proposal.sequence_ref}: "
                       f"created {len(created_pos)} draft PO(s)",
            'detail_json': json.dumps({
                'proposal_id': proposal.id,
                'action_type': proposal.action_type,
                'pos_created': [po.name for po in created_pos],
            }),
        })

        return execution
```

## Security Constraints

### Who Can Do What

| Action | Required Group | Notes |
|---|---|---|
| View proposals | `group_ai_user` | Own proposals only |
| Create proposals | System only | Via gateway tool results |
| Edit proposal lines | `group_ai_user` | Own proposals, draft/reviewed state only |
| Approve PO proposals | `purchase.group_purchase_manager` | Any user's proposals |
| Execute PO proposals | `purchase.group_purchase_manager` | Approved state only |
| Reject proposals | `group_ai_user` | Own, or manager for any |
| View all proposals | `group_ai_manager` | Read-only |
| Delete proposals | `group_ai_admin` | Only expired/rejected |

### Record Rules

```xml
<!-- Users see their own proposals -->
<record model="ir.rule" id="rule_proposal_user">
    <field name="name">Proposal: own proposals</field>
    <field name="model_id" ref="model_ai_analyst_action_proposal"/>
    <field name="domain_force">[('user_id','=',user.id)]</field>
    <field name="groups" eval="[(4, ref('group_ai_user'))]"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>

<!-- Purchase managers see all PO proposals for approval -->
<record model="ir.rule" id="rule_proposal_purchase_manager">
    <field name="name">Proposal: purchase managers see PO proposals</field>
    <field name="model_id" ref="model_ai_analyst_action_proposal"/>
    <field name="domain_force">[('action_type','=','purchase_order')]</field>
    <field name="groups" eval="[(4, ref('purchase.group_purchase_manager'))]"/>
</record>
```

### Hard Safety Guards

```python
# In action_execute():
# 1. NEVER call sudo() for creating business records
# 2. ALWAYS create in draft state
# 3. NEVER auto-confirm/validate
# 4. ALWAYS log execution with full details
# 5. ALWAYS verify proposal.state == 'approved' (double-check)
# 6. ALWAYS verify user has required groups (double-check)

# Additional safeguards:
assert proposal.state == 'approved', "SAFETY: Cannot execute non-approved proposal"
assert not proposal.executed_at, "SAFETY: Proposal already executed"

# PO is ALWAYS created in draft state — the standard Odoo PO workflow
# (confirm, receive, bill) handles the rest.
```

## Proposal Expiration

```python
# Cron job: daily
def _cron_expire_proposals(self):
    """Expire proposals that have not been acted upon."""
    expired = self.search([
        ('state', 'in', ['draft', 'reviewed']),
        ('expires_at', '<', fields.Datetime.now()),
    ])
    expired.write({'state': 'expired'})
    _logger.info("Expired %d stale proposals", len(expired))
```

## Future Action Types (Phase 4+)

| Action Type | Description | Required Group | Creates |
|---|---|---|---|
| `purchase_order` | Reorder suggestion → draft PO | `purchase.group_purchase_manager` | `purchase.order` (draft) |
| `stock_adjustment` | Inventory correction suggestion | `stock.group_stock_manager` | `stock.inventory` (draft) |
| `price_change` | Price list update suggestion | `product.group_sale_pricelist` | `product.pricelist.item` (draft) |
| `tag_assignment` | Product tag/season assignment | `group_ai_admin` | Batch `product.tag` assignment |

All future action types follow the same Propose → Approve → Execute pattern.

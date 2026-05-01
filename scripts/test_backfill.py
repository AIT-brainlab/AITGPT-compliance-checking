"""Quick test for predicate backfill logic."""
import sys
sys.path.insert(0, ".")
from langgraph_agent.nodes.fol import _backfill_predicates

# Test case 1: Good formula, bad action
test1 = {
    "deontic_formula": "O(payFee(student))",
    "predicates": {"subject": "x", "action": "Action", "condition": ""}
}
result1 = _backfill_predicates(test1)
print("Test 1: Good formula + bad action")
print(f"  Before: action=Action, subject=x")
print(f"  After:  action={result1['predicates']['action']}, subject={result1['predicates']['subject']}")
print()

# Test case 2: Good formula, action is fine
test2 = {
    "deontic_formula": "O(payFee(student))",
    "predicates": {"subject": "student", "action": "payFee", "condition": ""}
}
result2 = _backfill_predicates(test2)
print("Test 2: Good formula + good action (should not change)")
print(f"  action={result2['predicates']['action']}, subject={result2['predicates']['subject']}")
print()

# Test case 3: Empty predicates
test3 = {
    "deontic_formula": "F(disturbPeace(student))",
    "predicates": {"subject": "", "action": "", "condition": ""}
}
result3 = _backfill_predicates(test3)
print("Test 3: Empty predicates -> backfilled from formula")
print(f"  action={result3['predicates']['action']}, subject={result3['predicates']['subject']}")
print()

# Test case 4: No predicates key at all
test4 = {
    "deontic_formula": "O(attendOrientation(newStudent))",
}
result4 = _backfill_predicates(test4)
print("Test 4: No predicates key -> created from formula")
print(f"  action={result4['predicates']['action']}, subject={result4['predicates']['subject']}")

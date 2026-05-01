# LexDeMod External Validation (Mistral 7B)

A zero-shot classification evaluation on 150 random clauses from the LexDeMod test set.

- **Accuracy**: 0.3400
- **Macro F1**: 0.2085
- **Micro F1**: 0.3400

```text
              precision    recall  f1-score   support

        none       1.00      0.02      0.03        58
  obligation       0.34      1.00      0.51        45
  permission       1.00      0.09      0.17        44
 prohibition       0.08      0.33      0.12         3

    accuracy                           0.34       150
   macro avg       0.60      0.36      0.21       150
weighted avg       0.78      0.34      0.22       150

```

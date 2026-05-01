import sys
from pathlib import Path
import pandas as pd
import json
import re
from sklearn.metrics import classification_report, accuracy_score, f1_score
from tqdm import tqdm

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph_agent.nodes.classify import _build_prompt, _parse_response, _llm
from langchain_core.messages import HumanMessage

def map_label(lbl_str):
    try:
        arr = json.loads(lbl_str)
        # [O, E, Pro, Per, NO, NE, None]
        if arr[0] == 1: return 'obligation'
        if arr[2] == 1: return 'prohibition'
        if arr[1] == 1 or arr[3] == 1: return 'permission'
        return 'none'
    except Exception:
        return 'none'

def main():
    print("Loading LexDeMod test dataset...")
    df = pd.read_csv("research/LexDeMod/deontic_data/test_annotated_data.csv")
    
    df['target'] = df['label'].apply(map_label)
    
    # We take a stratified sample of 100 to execute quickly in this session
    # (Obligation 40, Permission 30, Prohibition 20, None 10)
    # The actual distribution might vary, so we'll just take a random sample of 150
    df_sample = df.sample(n=150, random_state=42)
    
    y_true = []
    y_pred = []
    
    for idx, row in tqdm(df_sample.iterrows(), total=len(df_sample), desc="Evaluating Mistral"):
        text = row['text']
        # remove prefix like [tenant] or [landlord]
        text = re.sub(r'^\[.*?\]\s*', '', text)
        
        target = row['target']
        
        item = {"text": text, "source": "LexDeMod"}
        hint = {"deontic_strength": "unknown", "speech_act": "unknown", "section_context": "unknown"}
        prompt = _build_prompt(item, hint)
        
        try:
            response = _llm.invoke([HumanMessage(content=prompt)])
            result = _parse_response(response.content)
            
            if not result.get("is_rule") or result.get("is_rule") == "False":
                pred = "none"
            else:
                pred = str(result.get("rule_type", "none")).lower()
                
        except Exception as e:
            pred = "none"
            
        if pred not in ['obligation', 'permission', 'prohibition', 'none']:
            pred = "none"
            
        y_true.append(target)
        y_pred.append(pred)
        
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average='macro', zero_division=0)
    micro_f1 = f1_score(y_true, y_pred, average='micro', zero_division=0)
    report = classification_report(y_true, y_pred, zero_division=0)
    
    print("\n--- LexDeMod Evaluation Results ---")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Macro F1:  {macro_f1:.4f}")
    print(f"Micro F1:  {micro_f1:.4f}")
    print("\nClassification Report:")
    print(report)
    
    # Write artifact
    with open("lexdemod_metrics.md", "w", encoding="utf-8") as f:
        f.write("# LexDeMod External Validation (Mistral 7B)\n\n")
        f.write("A zero-shot classification evaluation on 150 random clauses from the LexDeMod test set.\n\n")
        f.write(f"- **Accuracy**: {acc:.4f}\n")
        f.write(f"- **Macro F1**: {macro_f1:.4f}\n")
        f.write(f"- **Micro F1**: {micro_f1:.4f}\n\n")
        f.write("```text\n")
        f.write(report)
        f.write("\n```\n")
        
if __name__ == "__main__":
    main()

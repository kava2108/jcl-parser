# JCL to JSON Lightweight Parser

JCL の JOB / EXEC / DD ステートメントを簡易解析し、JSON 形式で出力する Python 製の軽量パーサーです。

汎用機アセンブラや JCL の解析を、GitHub 上で見える形にするための最小構成として公開しやすいようにまとめています。

公開アウトプットと技術テーマを短時間で把握できるよう、実装と外部リンクをコンパクトに整理しています。

---

## Features

- JOB / EXEC / DD を対象にした簡易パース
- KEY=VALUE 形式のパラメータ抽出（括弧・ネスト対応）
- `DISP=(NEW,CATLG,DELETE)` → 位置指定リストに変換
- `DCB=(RECFM=FB,LRECL=80)` → キーワードサブパラメータに変換
- `SPACE=(CYL,(10,5),RLSE)` → ネスト構造に変換
- `PARM=(OPT1,OPT2)` → リストに変換
- JOB → EXEC(steps) → DD(dds) の AST 形式で出力
- コメント行（//*）を無視
- JSON 形式で標準出力に出力
- 標準ライブラリのみで動作

---

## Usage

```bash
python jcl_parser.py sample.jcl
```

---

## Example

Input:

```jcl
//JOB1     JOB  CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//DD1      DD   DSN=TEST.FILE,DISP=SHR
//DD2      DD   DSN=NEW.FILE,DISP=(NEW,CATLG,DELETE),DCB=(RECFM=FB,LRECL=80)
```

Output:

```json
{
  "type": "JOB",
  "name": "JOB1",
  "params": { "CLASS": "A", "MSGCLASS": "X" },
  "steps": [
    {
      "type": "EXEC",
      "name": "STEP1",
      "params": { "PGM": "IEFBR14" },
      "dds": [
        {
          "type": "DD",
          "name": "DD1",
          "params": { "DSN": "TEST.FILE", "DISP": "SHR" }
        },
        {
          "type": "DD",
          "name": "DD2",
          "params": {
            "DSN": "NEW.FILE",
            "DISP": ["NEW", "CATLG", "DELETE"],
            "DCB": { "RECFM": "FB", "LRECL": "80" }
          }
        }
      ]
    }
  ]
}
```

---

## Publications

公開アウトプットの導線です。

- note: https://note.com/rascal2108
- Zenn: https://zenn.dev/rascal2108
- AI migration: https://www.rascal.biz/ai_migration.html

---

## Snapshot

- 目的: JCL を JSON に変換する最小パーサー
- 技術: Python の標準ライブラリのみで実装
- 対外発信: note / Zenn / AI migration ページへ誘導

---

## GitHub Actions への変換

```bash
python jcl_to_gha.py sample.jcl
```

JCL の各ステップを GitHub Actions の job に変換します。

| JCL | GitHub Actions |
|---|---|
| JOB | `name:` (ワークフロー名) |
| EXEC PGM= | job の `run:` コマンド |
| EXEC PARM= | `run:` への引数 |
| DD DSN= | job の `env:` (DD\_名前=DSN値) |
| 複数 EXEC | `needs:` で直列チェーン |

## Project Structure

- `jcl_parser.py`: JCL を JSON AST に変換する本体
- `jcl_models.py`: Pydantic モデル定義 (`--schema` で JSON Schema 出力)
- `jcl_to_gha.py`: AST を GitHub Actions YAML に変換
- `sample.jcl`: 動作確認用のサンプル
- `tests/test_jcl_parser.py`: 回帰テスト

---

## Future Work

- DD ライフサイクル対応（`DISP=(NEW,CATLG,DELETE)` → `upload-artifact` / `download-artifact` の自動挿入）
- JCL 条件制御（COND パラメータ）の解析と GHA の `if:` 条件への変換
- 継続行（カラム 72 折り返し）のサポート
- PROC / INCLUDE の展開
# jcl-parser

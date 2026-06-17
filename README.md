# JCL to JSON Lightweight Parser

JCL の JOB / EXEC / DD ステートメントを簡易解析し、JSON 形式で出力する Python 製の軽量パーサーです。

汎用機アセンブラや JCL の解析を、GitHub 上で見える形にするための最小構成として公開しやすいようにまとめています。

公開アウトプットと技術テーマを短時間で把握できるよう、実装と外部リンクをコンパクトに整理しています。

---

## Features

- JOB / EXEC / DD を対象にした簡易パース
- KEY=VALUE 形式のパラメータ抽出
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
```

Output:

```json
[
  {
    "type": "JOB",
    "name": "JOB1",
    "params": {
      "CLASS": "A",
      "MSGCLASS": "X"
    }
  }
]
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

## Project Structure

- `jcl_parser.py`: JCL を JSON に変換する本体
- `sample.jcl`: 動作確認用のサンプル
- `tests/test_jcl_parser.py`: 最低限の回帰テスト

---

## Future Work

- DD の詳細属性解析
- EXEC の複雑な PARM 表現への対応
- JCL 全体の AST 化
- スキーマ化してモダナイゼーション用途に拡張
# jcl-parser

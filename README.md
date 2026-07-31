# JCL to JSON Lightweight Parser

JCL の JOB / EXEC / DD ステートメントを簡易解析し、JSON 形式で出力する Python 製の軽量パーサーです。

汎用機アセンブラや JCL の解析を、GitHub 上で見える形にするための最小構成として公開しやすいようにまとめています。

公開アウトプットと技術テーマを短時間で把握できるよう、実装と外部リンクをコンパクトに整理しています。

---

## Features

- JOB / EXEC / DD / PROC / PEND / SET を対象にした簡易パース
- KEY=VALUE 形式のパラメータ抽出（括弧・ネスト対応）
- `DISP=(NEW,CATLG,DELETE)` → 位置指定リストに変換
- `DCB=(RECFM=FB,LRECL=80)` → キーワードサブパラメータに変換
- `SPACE=(CYL,(10,5),RLSE)` → ネスト構造に変換
- `PARM=(OPT1,OPT2)` → リストに変換
- 継続行（トレーリングカンマ・開き括弧未クローズ）のマージ
- 匿名DD（DD連結）・インストリームデータ（`DD *` / `DD DATA`）対応
- inline PROC/PEND 展開・シンボリックパラメータ（`&VAR`）置換・ステップ限定DDオーバーライド
- DSN依存関係解析（ジョブ内の読み書き順序グラフ）
- DISP/ENQ競合検出（重複NEW・削除後参照・未生成入力・ジョブ横断ENQ疑い）
- JOB → EXEC(steps) → DD(dds) の AST 形式で出力
- コメント行（//*）を無視
- JSON 形式で標準出力に出力
- 標準ライブラリ + Pydantic のみで動作

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

## 静的解析レイヤー (jcl_analyze.py)

```bash
python jcl_analyze.py job1.jcl [job2.jcl ...] [--proclib DIR ...]
```

PROC展開(inline + 外部PROCLIB) → DSN依存関係解析 → DISP/ENQ競合検出 を一括実行し、`warnings` / `dsn_usages` / `conflicts` を含む JSON レポートを出力します。複数ファイルを渡すとジョブ横断でのDSN競合(R4)も検出します。

`--proclib DIR` は繰り返し指定可能で、実際のPROCLIB連結と同様に先に指定したディレクトリが優先されます。ディレクトリ内のファイル名(大文字化)がプロシージャ名になり、`//name PROC ... PEND` を含むメンバーも、PROC/PENDを省略した素のEXEC/DD本体だけのメンバーも読み込めます。同名がJCL内のinline PROCにもある場合は、inline側が優先されます。

**検出ルール:**

| ルール | 内容 | severity |
|---|---|---|
| R1 | 同一DSNへの重複NEW(DELETE未経由) | error |
| R2 | ジョブ内で最初の参照がOLD/SHR/MOD(先行NEWなし) | info |
| R3 | 正常終了ディスポジションDELETE後の再参照 | error |
| R4 | 複数ジョブが同一DSNに排他DISP(OLD/NEW)を持つ | warning |
| R5 | DISP=(...,PASS) がジョブ内の後続ステップで一度も参照されない | warning |

**スコープ制限:**

- PROC解決は inline (`PROC`〜`PEND`) と `--proclib` で指定したディレクトリのみ対応。どちらにも見つからない参照は`warnings`に記録される
- ジョブ内のステップは順次実行される前提(COND による分岐・スキップは考慮しない)
- ジョブ横断のENQ競合(R4)は実行順序が不明なためヒューリスティックな警告であり、確定エラーではない

---

## Project Structure

- `jcl_parser.py`: JCL を JSON AST に変換する本体(継続行マージ・DD連結・インストリームデータを含む)
- `jcl_models.py`: Pydantic モデル定義 (`--schema` で JSON Schema 出力)
- `jcl_proc.py`: PROC/PEND 展開(inline + 外部PROCLIB)・シンボリックパラメータ置換
- `jcl_dsn.py`: DSN依存関係解析
- `jcl_disp_check.py`: DISP/ENQ競合検出ルール
- `jcl_analyze.py`: 静的解析レイヤーのCLIエントリポイント
- `jcl_to_gha.py`: AST を GitHub Actions YAML に変換
- `sample.jcl`: 動作確認用のサンプル
- `tests/`: 回帰テスト一式

---

## Future Work

- DD ライフサイクル対応(`DISP=(NEW,CATLG,DELETE)` → `upload-artifact` / `download-artifact` の自動挿入)
- JCL 条件制御(COND パラメータ)の解析と GHA の `if:` 条件への変換
- COND/RC分岐の意味解析(ステップ実行有無をモデル化し、DISP/ENQ検出の精度を上げる)
- ジョブ横断ENQの確定判定(実行スケジュール情報との連携が必要)
# jcl-parser

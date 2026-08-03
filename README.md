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
| DD DSN= | `jcl_dsn_path.py` でファイルパスに変換し job の `env:` (DD\_名前=パス) に設定 |
| DD DISP= | `jcl_file_ops.py` で `Prepare datasets` / `Finalize datasets` ステップの mkdir・rm 等に変換 |
| 複数 EXEC | `needs:` で直列チェーン |

**DSN→パス変換 (`jcl_dsn_path.py`):** `HLQ.MID.LOW` のような修飾子(`.`区切り)を `data/HLQ/MID/LOW` のようなディレクトリ階層に変換します(ベースディレクトリは `to_github_actions(model, base_dir=...)` で変更可)。PDS メンバーや GDG 相対世代 (`HLQ.PDS(MEMBER)` / `HLQ.GDG(+1)`) は括弧内を追加のパス要素として展開します(`data/HLQ/PDS/MEMBER` / `data/HLQ/GDG/+1`)。

**DISP→ファイル操作 (`jcl_file_ops.py`):** DISPの第1サブパラメータ(NEW/OLD/SHR/MOD)と正常終了時ディスポジション(第2サブパラメータ: CATLG/KEEP/DELETE/PASS)から、ステップ実行前後のシェルコマンドを生成します。

| DISP | 生成される操作 |
|---|---|
| NEW | 実行前に `mkdir -p` してファイルを作成 |
| OLD/SHR/MOD | 実行前に `test -e` で存在確認 |
| 正常終了時 DELETE | 実行後に `rm -f` |
| 正常終了時 CATLG/KEEP | 実行後の操作なし(パスに永続化) |
| 正常終了時 PASS | 操作なし(同一ジョブの後続ステップが同じパスを参照するため) |

異常終了時ディスポジション(第3サブパラメータ)は本ツールの「全ステップ正常終了」前提([jcl_analyze.py](jcl_analyze.py) の静的解析レイヤーと同じ前提)のもとでは使われません。

## 静的解析レイヤー (jcl_analyze.py)

```bash
python jcl_analyze.py job1.jcl [job2.jcl ...] [--proclib DIR ...]
```

PROC展開(inline + 外部PROCLIB) → IF/THEN/ELSE分岐のシナリオ展開 → DSN依存関係解析 → DISP/ENQ競合検出 を一括実行し、`warnings` / `dsn_usages` / `conflicts` を含む JSON レポートを出力します。複数ファイルを渡すとジョブ横断でのDSN競合(R4)も検出します。

`--proclib DIR` は繰り返し指定可能で、実際のPROCLIB連結と同様に先に指定したディレクトリが優先されます。ディレクトリ内のファイル名(大文字化)がプロシージャ名になり、`//name PROC ... PEND` を含むメンバーも、PROC/PENDを省略した素のEXEC/DD本体だけのメンバーも読み込めます。同名がJCL内のinline PROCにもある場合は、inline側が優先されます。

**条件分岐の扱い:** `// IF (...) THEN` / `// ELSE` / `// ENDIF` に加えて、個別EXEC文の `COND=(code,op[,step])` も「スキップされる/実行される」の2値分岐(SKIP/RUN)として扱われ、構文上排他な実行パス(シナリオ)としてモデル化されます([jcl_branch.py](jcl_branch.py))。各シナリオごとに独立してDSN解析・DISP競合検出が行われるため、THEN/ELSEやSKIP/RUNでそれぞれ別々に同じDSNをNEW作成しても、両方が同時には起こらないため誤検知しません。実際のRC値は静的解析では分からないため、「真偽どちらかは確定できないが、両方のシナリオを網羅する」というアプローチです。COND由来のDDには `conditional: true` も併せて付与されます。

**COND=EVEN / COND=ONLY の扱い:** この2つはRC比較ではなく「異常終了時のデフォルトバイパス挙動の変更」であり、本ツールは異常終了そのものをモデル化していません(全ステップが正常終了する前提)。その前提のもとでは、`COND=EVEN` は「異常終了後も実行する」という指定が実質意味を持たないため通常のステップと同様に扱い、`COND=ONLY`(単体でも `COND=((4,LT),ONLY)` のようにRCテストと併記されていても)は「異常終了後にのみ実行する」ため確定的に実行されないと判断し、そのステップをシナリオ分岐させずに解析対象から除外します(除外した旨は `warnings` に記録)。

**シナリオ数の安全弁:** COND=付きステップはレガシーJCLで大量に存在しうるため(ステップごとに前段RCをチェックする形が典型)、シナリオ数はデカルト積で爆発しえます。COND由来の分岐だけで合計シナリオ数が64([jcl_branch.py](jcl_branch.py) の `DEFAULT_MAX_SCENARIOS`)を超える場合、COND分岐だけを無効化して `conditional` フラグのみの従来動作にフォールバックし、`warnings` にその旨を記録します。ユーザーが明示的に書いた `IF/THEN/ELSE` はこの安全弁の対象外で、常に完全展開されます。

**検出ルール:**

| ルール | 内容 | severity |
|---|---|---|
| R1 | 同一DSN・同一シナリオ内での重複NEW(DELETE未経由) | error |
| R2 | ジョブ内で最初の参照がOLD/SHR/MOD(先行NEWなし) | info |
| R3 | 正常終了ディスポジションDELETE後の再参照 | error |
| R4 | 複数ジョブが同一DSNに排他DISP(OLD/NEW)を持つ | warning |
| R5 | DISP=(...,PASS) がジョブ内の後続ステップで一度も参照されない | warning |

**スコープ制限:**

- PROC解決は inline (`PROC`〜`PEND`) と `--proclib` で指定したディレクトリのみ対応。どちらにも見つからない参照は`warnings`に記録される
- 分岐外のステップは順次実行される前提(異常終了そのもの・そのデフォルトバイパス挙動はモデル化しない。`COND=EVEN`/`COND=ONLY` はこの前提の範囲内でのみ扱う)
- IF条件式の中身(`STEP1.RC = 0` など)は評価しない。構造的な排他性のみを利用する(連続・ネストしたIFの条件間の相関は考慮しない)
- ジョブ横断のENQ競合(R4)は実行順序が不明なためヒューリスティックな警告であり、確定エラーではない

---

## Project Structure

- `jcl_parser.py`: JCL を JSON AST に変換する本体(継続行マージ・DD連結・インストリームデータを含む)
- `jcl_models.py`: Pydantic モデル定義 (`--schema` で JSON Schema 出力)
- `jcl_proc.py`: PROC/PEND 展開(inline + 外部PROCLIB)・シンボリックパラメータ置換
- `jcl_branch.py`: IF/THEN/ELSE/ENDIF と COND= を排他シナリオへ分岐展開(シナリオ数上限つき)
- `jcl_dsn.py`: DSN依存関係解析(シナリオ・COND条件付きフラグ対応)
- `jcl_disp_check.py`: DISP/ENQ競合検出ルール
- `jcl_analyze.py`: 静的解析レイヤーのCLIエントリポイント
- `jcl_dsn_path.py`: DSN→ファイルパス変換
- `jcl_file_ops.py`: DISP→ファイル操作(mkdir/test -e/rm)への変換
- `jcl_to_gha.py`: AST を GitHub Actions YAML に変換(DSN→パス・DISP→ファイル操作を含む)
- `sample.jcl`: 動作確認用のサンプル
- `tests/`: 回帰テスト一式

---

## Future Work

- DD ライフサイクル対応の強化(現状は同一ランナー上のローカルファイル操作のみ。ステップをまたいでファイルを引き継ぐ `upload-artifact` / `download-artifact` の自動挿入)
- JCL 条件制御(COND パラメータ)の解析と GHA の `if:` 条件への変換
- 異常終了(ABEND)そのもののモデル化(現状は全ステップ正常終了を前提とした近似)
- ジョブ横断ENQの確定判定(実行スケジュール情報との連携が必要)
# jcl-parser

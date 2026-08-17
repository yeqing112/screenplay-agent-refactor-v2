# Git 仓库恢复说明

当前目录 `D:\Work\Project\screenplay-agent-refactor-v2` 下的 `.git` 目录不是一个可用仓库。

已确认的现状：

- `.git` 存在，但内部没有 `config`、`refs`、`objects` 等 Git 元数据。
- `git status` 会报 `fatal: not a git repository (or any of the parent directories): .git`。
- 工作目录里的项目文件是完整可用的，但 Git 历史和提交边界当前不可追踪。

这意味着问题不是“仓库脏了”，而是“仓库元数据缺失”。恢复时应优先保证现有代码文件不丢失。

## 恢复优先级

建议按下面顺序判断：

1. 是否有原始 `.git` 目录备份。
2. 是否知道原始远端仓库地址，且远端历史仍可访问。
3. 如果以上都没有，只能把当前目录作为一个新的 Git 仓库重新接管。

## 方案 A：有原始 `.git` 备份

这是最优方案，可以恢复完整历史、分支、tag 和提交边界。

操作思路：

1. 先关闭当前项目相关开发进程，避免文件占用。
2. 备份当前空 `.git` 目录。
3. 用原始 `.git` 目录覆盖回来。
4. 执行 `git status` 验证。

示例命令：

```powershell
Rename-Item -LiteralPath .git -NewName .git.broken
Copy-Item -Recurse -Force <你的备份路径>\.git .git
git status
git branch -a
git log --oneline -n 10
```

适用条件：

- 你本地别处有这个项目的完整仓库副本。
- 或者有 zip / 备份盘里的原始 `.git` 目录。

## 方案 B：知道远端仓库地址，但没有原始 `.git`

这个方案可以恢复远端历史，但要注意当前工作目录里已经有未提交修改，需要先保护好。

推荐做法：

1. 在同级目录重新 `clone` 一份干净仓库。
2. 把当前目录视作“工作副本”，只迁移业务文件，不覆盖新 clone 出来的 `.git`。
3. 用文件比对工具或手工复制，把当前修改同步到干净仓库。

示例流程：

```powershell
cd D:\Work\Project
git clone <远端仓库地址> screenplay-agent-refactor-v2-clean
```

然后：

1. 对比 `screenplay-agent-refactor-v2` 和 `screenplay-agent-refactor-v2-clean`。
2. 把当前新增或修改的文件迁到 `screenplay-agent-refactor-v2-clean`。
3. 在 `screenplay-agent-refactor-v2-clean` 中执行：

```powershell
git status
git add .
git commit -m "Restore local working tree changes"
```

适用条件：

- 你知道 GitHub / GitLab / Gitea 的仓库地址。
- 远端仓库还存在，且分支历史完整。

## 方案 C：没有备份，也不知道远端，只保留当前文件

这时无法恢复历史，只能把当前目录初始化成一个新的仓库。

这是“保住现状、从现在开始重新纳管”的方案。

建议先备份当前目录，再执行：

```powershell
Rename-Item -LiteralPath .git -NewName .git.broken
git init
git add .
git commit -m "Reinitialize repository from recovered working tree"
```

如果后续找到了远端地址，再补接：

```powershell
git remote add origin <远端仓库地址>
git branch -M main
git push -u origin main
```

风险说明：

- 原有提交历史无法恢复。
- blame、历史 diff、原始 PR 边界都会丢失。
- 之后只能从这次重新初始化的提交开始追踪。

## 不建议的做法

以下做法风险较高，不建议直接执行：

- 在当前空 `.git` 目录上手工补文件。
- 在不确认来源的情况下随意 `git init` 后强推到未知远端。
- 直接删除当前工作目录再重新拉取，容易丢失这轮已完成的本地改动。

## 当前项目建议

结合当前状态，建议优先采用下面顺序：

1. 先确认是否存在旧工作区、压缩包、备份盘或同事机器上的完整 `.git`。
2. 如果没有 `.git` 备份，再确认原始远端地址是否可找回。
3. 如果两者都没有，再执行“方案 C”重新初始化仓库。

## 恢复后建议立即验证

恢复完成后，至少执行：

```powershell
git status
git branch -a
git log --oneline -n 10
```

如果是方案 B 或 C，还建议补做一次构建与测试：

```powershell
cd web
npm test -- --run
npm run build
cd ..
python -m unittest discover -s tests -v
```

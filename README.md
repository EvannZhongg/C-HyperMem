# C-HyperMem: Composite Hypergraph Memory forLong-Term Conversational Agent Reasoning

## Git 后续提交操作流程

假设你的本地仓库已经和远程仓库关联好了（即 `origin/main` 已经设置）。

```powershell
git status  # 看哪些文件被修改了、哪些文件还没被 Git 跟踪。
git add .  # 添加所有修改的文件
git commit -m "简短清晰的提交说明"  # 交说明最好说明“做了什么改动”
git push origin main  # 推送到仓库
```

如果多人协作，先拉取远程更新再推送：

```powershell
git pull origin main --rebase  # `--rebase` 可以避免多余的合并提交，让历史更干净。
git push origin main  # 推送到仓库
```

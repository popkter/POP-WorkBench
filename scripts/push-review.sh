#!/usr/bin/env bash
# Push HEAD to refs/for/<branch> (Gerrit review).
# 目标分支由 NikoTools 表单选择；选项为当前已知分支，新增/删除分支后需更新下方 @choice 选项。

var branch=${目标分支@choice:develop=develop}

echo "Pushing HEAD to refs/for/${branch} ..."
git push origin "HEAD:refs/for/${branch}"

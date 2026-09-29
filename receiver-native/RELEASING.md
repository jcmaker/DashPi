# DashPi 앱 릴리스

Android 앱은 태그를 푸시하면 GitHub Actions가 서명된 APK를 만들어 GitHub Release로 올립니다.

Pi 없이 수신을 확인하려면 [테스트 QR](../docs/assets/optical-scan-check.png)을 다른 화면에 띄워 앱으로 비춥니다. 정상 수신 시 `scan-check.html` 검증 완료가 표시됩니다.

```bash
git checkout main && git pull
git tag app-v1.0.1        # MAJOR.MINOR.PATCH, minor/patch는 0-99
git push origin app-v1.0.1
```

- `.github/workflows/android-release.yml`이 버전을 `app.json`에 넣고(`versionCode`는 `1.0.1` → `10001`), 릴리스 빌드를 DashPi 업로드 키로 서명한 뒤 `DashPi.apk`를 릴리스에 첨부합니다. 서명 인증서 SHA-256이 다르면 릴리스를 만들지 않습니다.
- 릴리스가 나오면 Pages가 다시 배포되어 랜딩의 `/receiver/DashPi.apk`도 새 버전이 됩니다.
- 설치된 앱은 켜질 때와 다시 열릴 때 Releases에서 더 높은 `app-v*`를 찾습니다. 확인이 실패하거나 새 버전이 없으면 다음 번에 다시 확인합니다. "새 버전이 있어요"를 띄운 뒤에만 6시간 동안 다시 확인하지 않습니다. 오프라인이면 조용히 넘어갑니다.

## 서명 키

- GitHub Secrets: `DASHPI_UPLOAD_KEYSTORE_BASE64`, `DASHPI_UPLOAD_STORE_PASSWORD`, `DASHPI_UPLOAD_KEY_PASSWORD`, `DASHPI_UPLOAD_KEY_ALIAS`.
- 원본은 관리자 맥북의 `~/.config/dashpi/android-release.p12`와 `android-release.env`에 있습니다. **잃어버리면 이후 버전을 기존 앱 위에 설치할 수 없습니다.** 안전한 곳에 따로 백업하세요.
- 로컬 빌드는 이 키 없이 디버그 서명으로 만들어지므로 릴리스 APK와 서로 업데이트되지 않습니다.

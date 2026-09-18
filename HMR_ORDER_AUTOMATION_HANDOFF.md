# HMR 주문 현황 데이터 수집 자동화 — 인수인계 Context

## 1. 목표

판매채널별 주문·배송 데이터를 자동으로 수집하고 다음 이상 주문을 탐지한다.

- 배송준비 상태 6시간 이상 지속
- 발송 후 D+2 이상 배송 미완료
- 당일 송장 미등록 또는 채널 미전송
- 배송 실패, 오류 송장, 집화 실패
- 채널/WMS/ERP 간 주문·출고 상태 불일치
- 채널별 신규주문·배송준비·배송중·배송완료·구매확정 집계

API를 우선 사용하고, 공식 API가 없거나 필요한 데이터를 제공하지 않는 채널만 크롤링한다.

## 2. 원본 자료

요구사항 및 사이트 계정 목록:

```text
C:\Users\user1\Downloads\레포트사전확인요청_전략영업팀_SCM.xlsx
```

주의:

- 엑셀에 계정 ID/PW가 평문으로 포함되어 있다.
- 비밀번호를 코드, Git, 로그, 채팅에 출력하지 않는다.
- 운영 단계에서는 Secret Manager 또는 환경변수로 이전해야 한다.

## 3. 대상 채널과 API 조사 결과

공식 API 확인:

- 한촌몰/고도몰: NHN Commerce 주문·배송 API 제공
- 네이버 스마트스토어: Commerce API 제공
- 쿠팡 WING: 주문/발주서 API 제공
- 롯데ON: 주문·배송 Open API 제공
- CJ온스타일: 표준 주문·배송 REST API 제공
- 11번가: Seller API 제공
- 알리익스프레스: Seller Order API 제공

추가 확인 필요:

- G마켓·옥션 ESM: 공개 API 또는 계약/API 권한 확인 필요
- 아워박스 WMS: API/DB 접근 가능 여부 확인 필요
- ERP: 수주·납기·출고 데이터 접근 방식 확인 필요

네이버페이와 토스페이먼츠는 주문 채널이라기보다 결제·정산 보조 데이터로 분류한다.

## 4. 네이버 내부 API PoC

스마트스토어 대시보드 내부 API:

```http
GET https://sell.smartstore.naver.com/api/v1/sellers/dashboards/pay/order-delivery
```

한 번의 실제 호출에서 HTTP 200을 확인했다.

당시 안전하게 추출한 집계 예:

- `newOrderCases`: 8
- `deliveryPreparingCases`: 40
- `deliveringCases`: 252
- `deliveredCases`: 249

중요한 한계:

- undetected Chrome으로 ID/PW 입력까지 자동화했지만 CAPTCHA가 발생했다.
- 사용자가 CAPTCHA를 직접 해결한 후 로그인과 API 호출이 완료됐다.
- 따라서 완전 자동 로그인이 아니라 반자동 PoC다.
- CAPTCHA 우회 성공으로 표현하면 안 된다.
- 내부 API는 비공개이므로 URL/응답 구조 변경, 세션 만료, 접근 제한 위험이 있다.
- 내부 대시보드 API는 집계값 중심이므로 주문별 지연 판정에는 부족하다.

기존 PoC 코드:

```text
C:\Users\user1\Documents\HMR_Agent_Crawling\src\naver_internal_poc.py
```

테스트:

```text
C:\Users\user1\Documents\HMR_Agent_Crawling\test\test_naver_internal_poc.py
```

기존 `naver_crawling` 프로젝트에서 재사용한 구현:

```text
C:\Users\user1\.codex\worktrees\ec47\naver_crawling\scripts\python\smartplace_browser.py
```

사용한 방식:

- `undetected_chromedriver`
- 전용 Chrome 프로필
- 디버깅 포트 `9226`
- Chrome 150
- `create_uc_driver()`
- `naver_javascript_login()`

Python 환경:

```text
C:\Users\user1\anaconda3\envs\hanchon\python.exe
```

기존 PoC 실행 명령:

```powershell
C:\Users\user1\anaconda3\envs\hanchon\python.exe `
  C:\Users\user1\Documents\HMR_Agent_Crawling\src\naver_internal_poc.py `
  --port 9226
```

## 5. 네이버 공식 Commerce API 조사 결과

공식 API를 사용하면 필요한 주문 상세 데이터의 대부분을 수집할 수 있다.

Base URL:

```text
https://api.commerce.naver.com/external
```

OAuth 토큰:

```http
POST /v1/oauth2/token
```

인증 방식:

- OAuth 2.0 Client Credentials
- `client_id`
- `client_secret`을 이용한 bcrypt 전자서명
- Bearer Token
- 토큰 유효시간 약 3시간

최근 변경 주문 조회:

```http
GET /v1/pay-order/seller/product-orders/last-changed-statuses
```

주요 응답 필드:

- `orderId`
- `productOrderId`
- `productOrderStatus`
- `lastChangedType`
- `lastChangedDate`
- `paymentDate`
- `claimType`
- `claimStatus`

목록은 최대 300건이며 초과분은 다음 값으로 페이지 처리한다.

- `more.moreFrom`
- `more.moreSequence`

상품주문 상세 조회:

```http
POST /v1/pay-order/seller/product-orders/query
```

한 요청에 상품주문번호 최대 300개.

공식 문서상 확인된 주요 필드:

- `orderDate`
- `paymentDate`
- `placeOrderDate`
- `placeOrderStatus`
- `productOrderId`
- `productOrderStatus`
- `productName`
- `productOption`
- `quantity`
- `remainQuantity`
- `sellerProductCode`
- `shippingStartDate`
- `shippingDueDate`
- `deliveryCompany`
- `deliveryMethod`
- `deliveryStatus`
- 배송/송장 관련 정보
- 클레임 관련 정보

주요 상태:

- `PAYMENT_WAITING`
- `PAYED`
- `DELIVERING`
- `DELIVERED`
- `PURCHASE_DECIDED`
- `EXCHANGED`
- `CANCELED`
- `RETURNED`

배송 상세 상태 예:

- `COLLECT_REQUEST`
- `COLLECT_WAIT`
- `COLLECT_CARGO`
- `DELIVERING`
- `DELIVERY_COMPLETION`
- `DELIVERY_FAIL`
- `WRONG_INVOICE`
- `COLLECT_CARGO_FAIL`
- `NOT_TRACKING`

## 6. 공식 API로 구현할 판정 규칙 후보

배송준비 6시간 초과:

```text
productOrderStatus == PAYED
AND placeOrderStatus == OK
AND shippingStartDate가 없음
AND 현재시각 - 기준시각 >= 6시간
```

기준시각은 실제 응답을 확인한 뒤 `placeOrderDate` 또는 `lastChangedDate` 중 화면 정의와 맞는 값을 선택한다.

D+2 배송지연:

```text
productOrderStatus == DELIVERING
AND 현재시각 - shippingStartDate >= 2일
AND deliveryStatus != DELIVERY_COMPLETION
```

배송 이상:

```text
deliveryStatus IN (
  DELIVERY_FAIL,
  WRONG_INVOICE,
  COLLECT_CARGO_FAIL,
  COLLECT_CARGO_CANCEL
)
```

송장 미전송:

- 네이버 주문 상세의 송장번호 유무 확인
- 아워박스 WMS의 송장번호/출고 상태와 비교
- 네이버 단독 데이터만으로 WMS→채널 미전송 여부를 완전히 판정할 수는 없다.

## 7. 현재 공식 API 호출의 blocker

로컬에 다음 환경변수가 설정돼 있지 않다.

- `NAVER_COMMERCE_CLIENT_ID`
- `NAVER_COMMERCE_CLIENT_SECRET`

관련 `.env` 파일도 확인되지 않았다.

따라서 아직 공식 Commerce API의 실제 판매자 주문 응답은 호출하지 못했다. 지금까지 확인한 필드는 공식 문서 기준이다.

## 8. 새 프로젝트에서 가장 먼저 할 일

1. 네이버 커머스API센터에서 애플리케이션 등록
2. Client ID/Secret 발급
3. 비밀값을 Git 제외된 `.env`에 저장

예:

```dotenv
NAVER_COMMERCE_CLIENT_ID=...
NAVER_COMMERCE_CLIENT_SECRET=...
```

4. OAuth 토큰 발급 코드 구현
5. 최근 변경 주문 조회
6. 반환된 `productOrderId`로 상세 조회
7. 개인정보 값은 숨기고 필드명, 타입, 상태 관련 값만 검사
8. 실제 응답을 기준으로 배송준비/D+2/송장 판정 규칙 확정
9. 내부 API 집계와 공식 API 집계가 일치하는지 검산
10. 공식 API가 충분하면 내부 API 크롤링 PoC는 폐기

## 9. 실제 응답 검증 시 보안 규칙

출력 가능:

- HTTP 상태 코드
- 응답 필드명
- 데이터 타입
- 주문 상태 코드
- 필드 존재 여부
- 전체 건수와 집계값
- 날짜는 필요하면 마스킹 또는 상대 시간으로 출력

출력 금지:

- 주문자명
- 수령인명
- 전화번호
- 주소
- 배송 메모
- 출입 방법/공동현관 정보
- 주문번호 전체값
- 송장번호 전체값
- Client ID/Secret
- Access Token
- 로그인 쿠키

## 10. 권장 최종 구조

```text
네이버 Commerce API
  → 변경 주문 증분 수집
  → 주문 상세 조회
  → 원본 응답 암호화 저장 또는 필요한 필드만 저장
  → 주문상태 표준화
  → 지연·송장·배송 이상 판정
  → 대시보드 및 알림
```

아워박스 WMS/ERP 연동이 확보되면:

```text
채널 주문 + WMS 출고 + ERP 수주/출고
  → 주문번호/SKU 매칭
  → 상태 불일치 탐지
  → 미출고 및 송장 미전송 알림
```

## 11. 새 프로젝트 권장 우선순위

내부 API 자동 로그인을 더 확장하기보다 우선 Commerce API 키를 발급해 실제 주문 응답 스키마를 검증한다. 공식 API 응답이 요구사항을 충족하면 내부 API 크롤링은 검산 또는 비상 대체 수단으로만 유지한다.

import requests
import json
import pandas as pd
import time
from tenacity import retry, stop_after_attempt, wait_fixed

class MeroShare:
    def __init__(self, dmat_id=None, password=None, crn=None, pin=None, bank_name=None):
        if dmat_id and "-" in dmat_id:
            parts = dmat_id.split("-")
            self.dpid = parts[0][3:8]
            self.username = parts[1]

        self.password = password
        self.session = requests.Session()
        self.capital_id = self.get_capital_id()
        self.auth_token = None
        self.applicable_issues = None
        self.crn = crn
        self.pin = pin
        self.bank_name = bank_name

    def get_capital_id(self):
        url = "https://webbackend.cdsc.com.np/api/meroShare/capital/"
        res = self.session.get(url)
        if res.status_code == 200:
            for cap in res.json():
                if cap['code'] == self.dpid:
                    return cap['id']
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def login(self):
        if not self.capital_id:
            print("Capital ID not found")
            return False

        url = "https://webbackend.cdsc.com.np/api/meroShare/auth/"
        data = {
            "clientId": self.capital_id,
            "username": self.username,
            "password": self.password
        }

        res = self.session.post(url, json=data)
        if res.status_code == 200:
            self.auth_token = res.headers.get("Authorization")
            print("Login Success")
            return True
        print("Login Failed")
        return False

    def get_available_shares(self):
        url = "https://webbackend.cdsc.com.np/api/meroShare/companyShare/applicableIssue/"
        headers = {"Authorization": self.auth_token}

        res = self.session.post(url, headers=headers, json={"page": 1, "size": 10})
        if res.status_code == 200:
            data = res.json()
            self.applicable_issues = data.get("object", [])
            for s in self.applicable_issues:
                print(f"{s.get('scrip')} - {s.get('companyName')}")
            return self.applicable_issues
        return None

    def apply_for_share(self, script, qty):
        print(f"Applying for {script}...")

        issue = None
        for s in self.applicable_issues:
            if str(s.get("scrip")) == script:
                issue = s
                break

        if not issue:
            print("Invalid script")
            return False

        share_id = issue.get("companyShareId")

        # Get bank
        bank_list = self.session.get(
            "https://webbackend.cdsc.com.np/api/meroShare/bank/"
        ).json()

        bank_id = None
        for b in bank_list:
            if self.bank_name.lower() in b['name'].lower():
                bank_id = b['id']
                break

        if not bank_id:
            print("Bank not found")
            return False

        bank_details = self.session.get(
            f"https://webbackend.cdsc.com.np/api/meroShare/bank/{bank_id}"
        ).json()[0]

        payload = {
            "accountBranchId": bank_details.get("accountBranchId"),
            "accountNumber": bank_details.get("accountNumber"),
            "accountTypeId": bank_details.get("accountTypeId"),
            "appliedKitta": qty,
            "bankId": bank_id,
            "boid": self.username,
            "customerId": bank_details.get("id"),
            "crnNumber": self.crn,
            "companyShareId": share_id,
            "demat": f"130{self.dpid}{self.username}",
            "transactionPIN": self.pin
        }

        res = self.session.post(
            "https://webbackend.cdsc.com.np/api/meroShare/applicantForm/share/apply",
            json=payload
        )

        if res.status_code == 201:
            print("Applied Successfully")
            return True
        else:
            print("Application Failed", res.text)
            return False


def batch_apply(df, script, qty):
    results = []

    for _, row in df.iterrows():
        print(f"\nProcessing: {row['Name']}")
        ms = MeroShare(
            row['demat_id'],
            row['password'],
            row['crn'],
            row['pin'],
            row['Bank']
        )

        if ms.login():
            ms.get_available_shares()
            success = ms.apply_for_share(script, qty)
            status = "Success" if success else "Failed"
        else:
            status = "Login Failed"

        results.append({
            "Name": row['Name'],
            "Status": status
        })

        time.sleep(1)

    return pd.DataFrame(results)


if __name__ == "__main__":
    df = pd.read_excel("accounts.xlsx")

    script = input("Enter IPO Script: ")
    qty = int(input("Enter Quantity: "))

    result = batch_apply(df, script, qty)
    print(result)

    result.to_excel("result.xlsx", index=False)
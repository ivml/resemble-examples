import asyncio
import logging
import random
import send_email
from bank.v1.account_rsm import Account
from bank.v1.bank_rsm import (
    Bank,
    BankState,
    SignUpRequest,
    SignUpResponse,
    TransferRequest,
    TransferSuccessEmailTaskRequest
)
from bank.v1.errors_rsm import OverdraftError
from google.protobuf.empty_pb2 import Empty
from resemble.aio.contexts import TransactionContext, WriterContext

logging.basicConfig(level=logging.INFO)


class BankServicer(Bank.Interface):

    async def pick_new_account_id(self, context: TransactionContext) -> str:
        """Picks an account ID for a new account."""
        # Transactions normally observe state through Reader calls. However for
        # convenience, it is possible to do an inline read of the state of this
        # state machine, which is like calling a Reader that simply returns the
        # whole state of the state machine.
        state = await self.read(context)
        while True:
            new_account_id = str(random.randint(1000000, 9999999))
            if new_account_id not in state.account_ids:
                return new_account_id

    async def SignUp(
        self,
        context: TransactionContext,
        request: SignUpRequest,
    ) -> SignUpResponse:

        new_account_id = await self.pick_new_account_id(context)

        # Transactions can alter state only through Writer calls. For
        # convenience, it is possible to define an "inline writer" function. It
        # has all the same semantics as a Writer call, but...
        # 1. It doesn't get a request; it can access the scope it has been
        #    defined in directly.
        # 2. It doesn't return a response; it can modify the scope it has been
        #    defined in.
        async def add_account(
            context: WriterContext,
            state: BankState,
        ) -> Bank.Effects:
            state.account_ids.append(new_account_id)
            return Bank.Effects(state=state)

        await self.write(context, add_account)

        # Let's go create the account.
        account = Account(new_account_id)
        await account.Open(context, customer_name=request.customer_name)

        return SignUpResponse(account_id=new_account_id)

    async def Transfer(
        self,
        context: TransactionContext,
        request: TransferRequest,
    ) -> Empty:
        from_account = Account(request.from_account_id)
        to_account = Account(request.to_account_id)
        await from_account.Withdraw(context, amount=request.amount)
        await to_account.Deposit(context, amount=request.amount)

        async def send_confirmation_email(
            context: WriterContext,
            state: BankState,
        ) -> Bank.Effects:
            transfer_email = self.schedule().TransferSuccessEmailTask(context, from_account_id=request.from_account_id, to_account_id=request.to_account_id, amount=request.amount)
            return Bank.Effects(
                state=state,
                tasks=[transfer_email],
                response=Empty(),
            )

        await self.write(context, send_confirmation_email)

        return Empty()

    async def TransferSuccessEmailTask(
        self,
        context: WriterContext,
        state: BankState,
        request: TransferSuccessEmailTaskRequest,
    ) -> Bank.TransferSuccessEmailTaskEffects:
        from_account = Account(request.from_account_id)
        to_account = Account(request.to_account_id)

        print('from_account', from_account)

        from_customer_name = await from_account.Name(context)
        to_customer_name = await to_account.Name(context)

        message_body = (
            f"Transfer for '{request.amount}' DKK from '{from_customer_name}' to '{to_customer_name}' successful\n"
            "Best regards,\n"
            "Your Bank"
        )

        await send_email.send_email(message_body)

        return Bank.TransferSuccessEmailTaskEffects(
            state=state,
            response=Empty(),
        )
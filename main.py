import os
from datetime import datetime
from decimal import Decimal
from typing import List, Dict

from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import (
    sessionmaker,
    declarative_base,
    relationship,
    Session,
)

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)

    orders = relationship("Order", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer {self.first_name} {self.last_name} ({self.email})>"


class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    def __repr__(self) -> str:
        return f"<Product {self.product_name} — ${self.price}>"


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    order_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Order #{self.order_id} Total=${self.total_amount}>"


class OrderItem(Base):
    __tablename__ = "orderitems"

    order_item_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.order_id", ondelete="cascade"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.product_id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

    def __repr__(self) -> str:
        return f"<OrderItem qty={self.quantity} subtotal=${self.subtotal}>"



DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://store_user:store_pass@localhost:5432/store_db",
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    Base.metadata.create_all(engine)


def place_order(
    session: Session,
    customer_id: int,
    items: List[Dict[str, object]],
) -> Order:
    try:
        order = Order(
            customer_id=customer_id,
            order_date=datetime.utcnow(),
            total_amount=0,
        )
        session.add(order)
        session.flush()

        total = Decimal("0.00")
        for item in items:
            product = session.query(Product).filter_by(
                product_id=item["product_id"]
            ).one()

            quantity = item["quantity"]
            subtotal = product.price * quantity

            order_item = OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=quantity,
                subtotal=subtotal,
            )
            session.add(order_item)
            total += subtotal

        order.total_amount = total
        session.commit()

        print(f"Заказ #{order.order_id} размещён. Итого: ${order.total_amount}")
        return order

    except Exception:
        session.rollback()
        raise


def update_customer_email(
    session: Session,
    customer_id: int,
    new_email: str,
) -> Customer:
    try:
        customer = session.query(Customer).filter_by(
            customer_id=customer_id
        ).one()

        old_email = customer.email
        customer.email = new_email
        session.commit()

        print(f"Email клиента #{customer_id} изменён:")
        print(f"   {old_email} -> {new_email}")
        return customer

    except Exception:
        session.rollback()
        raise


def add_product(
    session: Session,
    product_name: str,
    price: float | Decimal,
) -> Product:
    try:
        product = Product(
            product_name=product_name,
            price=Decimal(str(price)),
        )
        session.add(product)
        session.commit()

        print(f"Продукт '{product_name}' добавлен (ID={product.product_id})")
        return product

    except Exception:
        session.rollback()
        raise


def demo() -> None:
    session = SessionLocal()

    try:
        p1 = add_product(session, "Ноут", 114)
        p2 = add_product(session, "Мышь", 1000)
        p3 = add_product(session, "машина тайота", 4500)

        customer = Customer(
            first_name="Иван",
            last_name="иванов",
            email="ivan@gmail.com",
        )
        session.add(customer)
        session.commit()

        update_customer_email(session, customer.customer_id, "ivan.petrov@mail.ru")

        order = place_order(
            session,
            customer_id=customer.customer_id,
            items=[
                {"product_id": p1.product_id, "quantity": 1},
                {"product_id": p2.product_id, "quantity": 2},
                {"product_id": p3.product_id, "quantity": 1},
            ],
        )
        print()
        print("  Детали заказа:")
        for item in order.items:
            prod = session.query(Product).filter_by(
                product_id=item.product_id
            ).one()
            print(f"  {prod.product_name} × {item.quantity} = ${item.subtotal}")
        print(f"  ИТОГО: ${order.total_amount}")

    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    demo()

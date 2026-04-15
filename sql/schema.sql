create table if not exists customers (
    customer_id serial primary key,
    first_name varchar(100) not null,
    last_name varchar(100) not null,
    email varchar(255) unique not null
);

create table if not exists products (
    product_id serial primary key,
    product_name varchar(255) not null,
    price decimal(10, 2) not null check (price >= 0)
);

create table if not exists orders (
    order_id serial primary key,
    customer_id integer not null references customers(customer_id),
    order_date timestamp not null default now(),
    total_amount decimal(10, 2) not null default 0
);

create table if not exists orderitems (
    order_item_id serial primary key,
    order_id integer not null references orders(order_id) on delete cascade,
    product_id integer not null references products(product_id),
    quantity integer not null check (quantity > 0),
    subtotal decimal(10, 2) not null
);

begin;

insert into orders (customer_id, order_date, total_amount)
values (1, now(), 0);

insert into orderitems (order_id, product_id, quantity, subtotal)
select
    currval('orders_order_id_seq'),
    p.product_id,
    x.qty,
    p.price * x.qty
from (values (1, 2), (2, 1)) as x(product_id, qty)
join products p on p.product_id = x.product_id;

update orders
set total_amount = (
    select coalesce(sum(subtotal), 0)
    from orderitems
    where order_id = currval('orders_order_id_seq')
)
where order_id = currval('orders_order_id_seq');

commit;

begin;

update customers
set email = 'new.email@gmail.com'
where customer_id = 1;

commit;

begin;

insert into products (product_name, price)
values ('новый товар', 999.99);

commit;

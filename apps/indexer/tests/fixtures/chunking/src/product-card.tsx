import { api } from "./api";

export const formatPrice = (value: number) => `$${value}`;

export const useProduct = (id: string) => {
  return api.load(id);
};

export function ProductCard({ title, price }: { title: string; price: number }) {
  return <section>{title} {formatPrice(price)}</section>;
}

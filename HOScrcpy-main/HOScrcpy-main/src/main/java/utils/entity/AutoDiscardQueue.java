package utils.entity;

import java.util.LinkedList;

public class AutoDiscardQueue<E> extends LinkedList<E> {
    private final int capacity;

    public AutoDiscardQueue(int capacity) {
        this.capacity = capacity;
    }

    @Override
    public boolean offer(E e) {
        if (size() >= capacity) {
            poll();
        }
        return super.offer(e);
    }
}
